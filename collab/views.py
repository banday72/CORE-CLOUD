"""Views for the internal collaboration app (Mail, Chat, Meetings)."""

from html import escape as html_escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from employees.decorators import permission_required
from employees.models import Department, Employee

from .access import accessible_employees, blocked_features, is_blocked
from .models import (
    FORWARD_STYLE_CHOICES, FORWARD_STYLE_QUOTE,
    MAIL_TYPE_CHOICES, MAIL_TYPE_HTML, MAIL_TYPE_PLAIN,
    FEATURE_CHAT, FEATURE_MAIL, FEATURE_MEETINGS,
    ChatMessage, Conversation, ConversationMember,
    MailMessage, MailRecipient, MailSettings, Meeting, MeetingAttendee,
)
from .sanitize import clean_html, html_to_text, message_html, plain_to_html


def _me(request):
    return getattr(request.user, 'employee', None)


def _require_me(request):
    """Return the current Employee or None (after queueing an error message)."""
    me = _me(request)
    if me is None:
        messages.error(request, 'No employee profile is linked to this account.')
    return me


def _guard_feature(request, feature):
    """Return the current Employee, or a redirect response when blocked.

    Usage: ``guarded = _guard_feature(request, FEATURE_MAIL);
    if isinstance(guarded, HttpResponse): return guarded``.
    """
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    if is_blocked(me, feature):
        messages.error(
            request,
            f'Your {feature} access has been restricted by the IT/Networks team. '
            f'Contact them to restore access.',
        )
        return redirect('dashboard')
    return me


def _active_employees(exclude=None):
    qs = Employee.objects.filter(status='active').select_related('department').order_by('first_name', 'last_name')
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


def _employee_data(me):
    return [
        {
            'id': e.pk,
            'name': e.full_name,
            'designation': e.designation or '',
            'dept': e.department.name if e.department else '',
            'emp_id': e.employee_id,
        }
        for e in accessible_employees(FEATURE_MAIL, exclude=me)
    ]


# ---------------------------------------------------------------------------
# Mail (Outlook-like)
# ---------------------------------------------------------------------------

@login_required
def mail_inbox(request):
    me = _guard_feature(request, FEATURE_MAIL)
    if not isinstance(me, Employee):
        return me
    items = (MailRecipient.objects
             .filter(employee=me, is_deleted=False)
             .select_related('mail', 'mail__sender'))
    unread = items.filter(is_read=False).count()
    return render(request, 'collab/mail_inbox.html', {
        'items': items, 'unread': unread, 'collab_tab': 'mail_inbox',
        'employee_count': _active_employees(me).count(),
    })


@login_required
def mail_sent(request):
    me = _guard_feature(request, FEATURE_MAIL)
    if not isinstance(me, Employee):
        return me
    mails = (MailMessage.objects
             .filter(sender=me)
             .prefetch_related('recipients__employee'))
    return render(request, 'collab/mail_sent.html', {
        'mails': mails, 'collab_tab': 'mail_sent',
    })


def _can_access_mail(me, mail):
    if mail.sender_id == me.pk:
        return True
    return mail.recipients.filter(employee=me).exists()


def _dedupe(ids):
    return list(dict.fromkeys(ids))


def _notify_recipients(me, mail):
    """Email everyone on a mail (best-effort; never raises)."""
    try:
        from hr_modules.emails import send_ticket_email
    except Exception:
        return
    body_text = html_to_text(mail.body) if mail.mail_type == MAIL_TYPE_HTML else mail.body
    seen = set()
    for rec in mail.recipients.select_related('employee'):
        emp = rec.employee
        if not emp or emp.pk in seen:
            continue
        seen.add(emp.pk)
        try:
            send_ticket_email(
                emp,
                f'[CoreCloud Mail] {mail.subject}',
                f'You have a new internal message from {me.full_name}.\n\n'
                f'{body_text}\n\n— Sent via CoreCloud internal mail.',
            )
        except Exception:
            pass


def _body_html(msg):
    """Full HTML of a stored message: its body plus accumulated quote history."""
    return message_html(msg.body, msg.mail_type, msg.quoted)


def _reply_quote_html(parent):
    """Outlook-style quoted block shown under a reply box."""
    stamp = parent.created_at.strftime('%b %d, %Y %H:%M')
    sender_name = parent.sender.full_name if parent.sender else 'System'
    header = f'<div class="quote-header">On {stamp}, {sender_name} wrote:</div>'
    return header + _body_html(parent)


def _forward_quote_html(parent):
    """Outlook-style forwarded block (or a simple quote, per HR settings)."""
    settings = MailSettings.get()
    if settings.forward_style == FORWARD_STYLE_QUOTE:
        text = html_to_text(_body_html(parent))
        quoted = '\n'.join('> ' + line for line in text.splitlines())
        return plain_to_html(quoted)

    sender = parent.sender
    sender_name = sender.full_name if sender else 'System'
    from_email = (sender.email if sender else '') or ''
    stamp = parent.created_at.strftime('%b %d, %Y %H:%M')
    to_names = ', '.join(
        r.employee.full_name
        for r in parent.recipients.select_related('employee')
        if r.kind == MailRecipient.KIND_TO
    ) or '—'
    sender_line = html_escape(sender_name)
    if from_email:
        sender_line += f' &lt;{html_escape(from_email)}&gt;'
    meta = (
        f'<div class="quote-meta">From: {sender_line}<br>'
        f'Date: {stamp}<br>'
        f'Subject: {html_escape(parent.subject or "")}<br>'
        f'To: {html_escape(to_names)}</div>'
    )
    return (
        '<div class="quote-header">---------- Forwarded message ----------</div>'
        + meta + _body_html(parent)
    )


def _build_quote(parent, quote_mode):
    if quote_mode == 'forward':
        return _forward_quote_html(parent)
    return _reply_quote_html(parent)


def _apply_signature(body, mail_type):
    """Append the HR-configured signature to an outgoing message body."""
    settings = MailSettings.get()
    sig = (settings.signature or '').strip()
    if not settings.use_signature or not sig:
        return body
    if mail_type == MAIL_TYPE_HTML:
        return f'{body}<div class="mail-signature"><br>--<br>{plain_to_html(sig)}</div>'
    return f'{body}\n\n-- \n{sig}'


@login_required
def mail_compose(request):
    me = _guard_feature(request, FEATURE_MAIL)
    if not isinstance(me, Employee):
        return me

    prefs = MailSettings.get()
    mode = request.GET.get('mode', 'reply')
    parent = None
    initial_to = []
    initial_cc = []
    initial_subject = ''
    initial_body = ''
    initial_quote = ''
    quote_mode = ''
    mail_type = prefs.default_mail_type

    if request.method == 'POST':
        subject = (request.POST.get('subject') or '').strip()
        raw_body = (request.POST.get('body') or '').strip()
        mail_type = request.POST.get('mail_type')
        if mail_type != MAIL_TYPE_HTML:
            mail_type = MAIL_TYPE_PLAIN
        body = clean_html(raw_body) if mail_type == MAIL_TYPE_HTML else raw_body
        to_ids = set(int(x) for x in request.POST.getlist('recipients') if x.isdigit())
        cc_ids = set(int(x) for x in request.POST.getlist('cc_recipients') if x.isdigit())

        dept_id = request.POST.get('department')
        if dept_id and dept_id.isdigit():
            to_ids |= set(
                Employee.objects.filter(status='active', department_id=int(dept_id))
                .values_list('pk', flat=True)
            )
        if request.POST.get('all_active'):
            to_ids |= set(
                Employee.objects.filter(status='active').values_list('pk', flat=True)
            )

        to_ids.discard(me.pk)
        cc_ids.discard(me.pk)
        cc_ids -= to_ids

        parent_id = request.POST.get('parent') or ''
        if parent_id.isdigit():
            parent = MailMessage.objects.filter(pk=int(parent_id)).first()

        if mail_type == MAIL_TYPE_HTML:
            has_body = bool(html_to_text(body).strip())
        else:
            has_body = bool(body.strip())

        if not subject or not has_body or not (to_ids or cc_ids):
            messages.error(request, 'Subject, message and at least one recipient are required.')
            initial_to = sorted(to_ids)
            initial_cc = sorted(cc_ids)
            initial_subject = subject
            initial_body = raw_body
            quote_mode = request.POST.get('quote_mode') or ''
            if parent and request.POST.get('include_quote') == '1':
                initial_quote = _build_quote(parent, quote_mode or 'reply')
        else:
            recipients_to = list(Employee.objects.filter(pk__in=to_ids, status='active'))
            recipients_cc = list(Employee.objects.filter(pk__in=cc_ids, status='active'))
            quote_mode = request.POST.get('quote_mode') or 'reply'
            include_quote = request.POST.get('include_quote') == '1'
            if quote_mode != 'forward':
                include_quote = include_quote and prefs.include_quote_in_reply
            quoted = _build_quote(parent, quote_mode) if (parent and include_quote) else ''
            mail = MailMessage.objects.create(
                sender=me, subject=subject,
                body=_apply_signature(body, mail_type),
                mail_type=mail_type, quoted=quoted, parent=parent,
            )
            rows = [
                MailRecipient(mail=mail, employee=emp, kind=MailRecipient.KIND_TO)
                for emp in recipients_to
            ]
            rows += [
                MailRecipient(mail=mail, employee=emp, kind=MailRecipient.KIND_CC)
                for emp in recipients_cc
            ]
            MailRecipient.objects.bulk_create(rows)
            _notify_recipients(me, mail)
            messages.success(
                request,
                f'Message sent to {len(recipients_to) + len(recipients_cc)} recipient(s).',
            )
            return redirect('collab_mail_sent')

    elif request.GET.get('reply_to', '').isdigit():
        parent = (MailMessage.objects
                  .filter(pk=int(request.GET['reply_to']))
                  .select_related('sender')
                  .first())
        if parent and _can_access_mail(me, parent):
            subject = parent.subject or ''
            if mode == 'forward':
                initial_subject = subject if subject.lower().startswith('fwd:') else f'Fwd: {subject}'
                quote_mode = 'forward'
                initial_quote = _build_quote(parent, 'forward')
            else:
                initial_subject = subject if subject.lower().startswith('re:') else f'Re: {subject}'
                others = [
                    r.employee_id for r in parent.recipients.select_related('employee')
                    if r.employee_id != me.pk
                ]
                sender = parent.sender
                if mode == 'reply_all':
                    if sender and sender.pk != me.pk:
                        initial_to.append(sender.pk)
                    initial_to.extend(others)
                elif mode == 'cc':
                    if sender and sender.pk != me.pk:
                        initial_to.append(sender.pk)
                    initial_cc = others
                else:
                    if sender and sender.pk != me.pk:
                        initial_to = [sender.pk]
                quote_mode = 'reply'
                if prefs.include_quote_in_reply:
                    initial_quote = _build_quote(parent, 'reply')
        else:
            parent = None

    initial_to = _dedupe(initial_to)
    initial_cc = [i for i in _dedupe(initial_cc) if i not in initial_to]

    return render(request, 'collab/mail_compose.html', {
        'employee_data': _employee_data(me),
        'departments': Department.objects.all(),
        'initial_to': initial_to,
        'initial_cc': initial_cc,
        'initial_subject': initial_subject,
        'initial_body': initial_body,
        'quote_html': initial_quote,
        'quote_mode': quote_mode,
        'mail_type': mail_type,
        'parent': parent,
        'collab_tab': 'mail_compose',
    })


@login_required
def mail_reply(request, pk, mode='reply'):
    me = _guard_feature(request, FEATURE_MAIL)
    if not isinstance(me, Employee):
        return me
    mail = get_object_or_404(MailMessage, pk=pk)
    if not _can_access_mail(me, mail):
        messages.error(request, 'You do not have access to that message.')
        return redirect('collab_mail')
    return redirect(f"{reverse('collab_mail_compose')}?reply_to={pk}&mode={mode}")


def _reply_variants(me, mail, to_recipients, cc_recipients):
    """Pre-built Reply / Reply all / Forward fields (Outlook-like inline reply).

    ``body`` is intentionally empty: the user only types their own words.
    ``quote`` carries the separate, deletable quoted-message HTML block.
    """
    prefs = MailSettings.get()
    sender = mail.sender
    subject = mail.subject or ''
    re_subject = subject if subject.lower().startswith('re:') else f'Re: {subject}'
    fwd_subject = subject if subject.lower().startswith('fwd:') else f'Fwd: {subject}'

    sender_only = [sender] if (sender and sender.pk != me.pk) else []
    reply_all_to = _dedupe([e.pk for e in sender_only] + [e.pk for e in to_recipients if e.pk != me.pk])
    reply_all_cc = [e.pk for e in cc_recipients if e.pk != me.pk and e.pk not in reply_all_to]

    reply_quote = _reply_quote_html(mail) if prefs.include_quote_in_reply else ''

    return {
        'reply': {
            'to': [e.pk for e in sender_only], 'cc': [],
            'subject': re_subject, 'quote': reply_quote, 'mode': 'reply',
        },
        'reply_all': {
            'to': reply_all_to, 'cc': reply_all_cc,
            'subject': re_subject, 'quote': reply_quote, 'mode': 'reply',
        },
        'forward': {
            'to': [], 'cc': [],
            'subject': fwd_subject, 'quote': _forward_quote_html(mail),
            'mode': 'forward',
        },
    }


@login_required
def mail_detail(request, pk):
    me = _guard_feature(request, FEATURE_MAIL)
    if not isinstance(me, Employee):
        return me
    rec = get_object_or_404(
        MailRecipient.objects.select_related('mail', 'mail__sender'),
        pk=pk, employee=me, is_deleted=False,
    )
    if not rec.is_read:
        rec.is_read = True
        rec.read_at = timezone.now()
        rec.save(update_fields=['is_read', 'read_at'])
    recipients = list(rec.mail.recipients.select_related('employee'))
    to_recipients = [r.employee for r in recipients if r.kind == MailRecipient.KIND_TO]
    cc_recipients = [r.employee for r in recipients if r.kind == MailRecipient.KIND_CC]
    return render(request, 'collab/mail_detail.html', {
        'rec': rec, 'mail': rec.mail, 'collab_tab': 'mail_inbox',
        'to_recipients': to_recipients, 'cc_recipients': cc_recipients,
        'employee_data': _employee_data(me),
        'reply_variants': _reply_variants(me, rec.mail, to_recipients, cc_recipients),
        'mail_type': MailSettings.get().default_mail_type,
    })


@login_required
@permission_required('manage_mail_settings')
def mail_settings(request):
    """HR-only preferences for the internal mail module."""
    prefs = MailSettings.get()
    if request.method == 'POST':
        prefs.include_quote_in_reply = request.POST.get('include_quote_in_reply') == '1'
        prefs.use_signature = request.POST.get('use_signature') == '1'
        prefs.signature = (request.POST.get('signature') or '').strip()
        mail_type = request.POST.get('default_mail_type')
        if mail_type in dict(MAIL_TYPE_CHOICES):
            prefs.default_mail_type = mail_type
        forward_style = request.POST.get('forward_style')
        if forward_style in dict(FORWARD_STYLE_CHOICES):
            prefs.forward_style = forward_style
        prefs.save()
        messages.success(request, 'Mail settings saved.')
        return redirect('collab_mail_settings')
    return render(request, 'collab/mail_settings.html', {
        'prefs': prefs, 'collab_tab': 'mail_settings',
        'mail_type_choices': MAIL_TYPE_CHOICES,
        'forward_style_choices': FORWARD_STYLE_CHOICES,
    })


@require_POST
@login_required
def mail_delete(request, pk):
    me = _guard_feature(request, FEATURE_MAIL)
    if not isinstance(me, Employee):
        return me
    rec = get_object_or_404(MailRecipient, pk=pk, employee=me)
    rec.is_deleted = True
    rec.save(update_fields=['is_deleted'])
    messages.success(request, 'Message moved to trash.')
    return redirect('collab_mail')


# ---------------------------------------------------------------------------
# Chat (Teams-like)
# ---------------------------------------------------------------------------

@login_required
def chat_home(request, conv_id=None):
    me = _guard_feature(request, FEATURE_CHAT)
    if not isinstance(me, Employee):
        return me

    conv_list = []
    for conv in Conversation.objects.filter(members__employee=me).prefetch_related('members__employee'):
        last = conv.messages.order_by('-created_at').first()
        membership = conv.members.filter(employee=me).first()
        unread_qs = conv.messages.exclude(sender=me)
        if membership and membership.last_read_at:
            unread_qs = unread_qs.filter(created_at__gt=membership.last_read_at)
        conv_list.append({
            'conv': conv,
            'title': conv.display_title(me),
            'last': last,
            'unread': unread_qs.count(),
            'ts': last.created_at if last else conv.created_at,
        })
    conv_list.sort(key=lambda row: row['ts'], reverse=True)

    active = None
    active_title = ''
    active_messages = []
    participants = []
    if conv_id is not None:
        active = get_object_or_404(Conversation, pk=conv_id, members__employee=me)
        active_title = active.display_title(me)
        active_messages = list(active.messages.select_related('sender'))
        memberships = active.members.select_related('employee')
        participants = [m.employee for m in memberships]
        my_membership = active.members.filter(employee=me).first()
        if my_membership:
            unread_qs = active.messages.exclude(sender=me)
            if my_membership.last_read_at:
                unread_qs = unread_qs.filter(created_at__gt=my_membership.last_read_at)
            if unread_qs.exists():
                my_membership.last_read_at = timezone.now()
                my_membership.save(update_fields=['last_read_at'])
            else:
                my_membership.last_read_at = timezone.now()
                my_membership.save(update_fields=['last_read_at'])

    return render(request, 'collab/chat.html', {
        'conv_list': conv_list,
        'active': active,
        'active_title': active_title,
        'active_messages': active_messages,
        'participants': participants,
        'employees': accessible_employees(FEATURE_CHAT, exclude=me),
        'collab_tab': 'chat',
    })


@require_POST
@login_required
def chat_start_direct(request):
    me = _guard_feature(request, FEATURE_CHAT)
    if not isinstance(me, Employee):
        return me
    other = get_object_or_404(
        Employee.objects.filter(status='active'),
        pk=request.POST.get('employee') or 0,
    )
    if is_blocked(other, FEATURE_CHAT):
        messages.error(
            request,
            f'{other.full_name}\'s Chat access is restricted by the IT/Networks team.',
        )
        return redirect('collab_chat')
    if other.pk == me.pk:
        messages.error(request, 'You cannot start a chat with yourself.')
        return redirect('collab_chat')
    conv = (Conversation.objects
            .filter(kind=Conversation.KIND_DIRECT, members__employee=me)
            .filter(members__employee=other)
            .first())
    if conv is None:
        conv = Conversation.objects.create(kind=Conversation.KIND_DIRECT, created_by=me)
        ConversationMember.objects.create(conversation=conv, employee=me)
        ConversationMember.objects.create(conversation=conv, employee=other)
    return redirect('collab_chat_room', conv_id=conv.pk)


@require_POST
@login_required
def chat_start_group(request):
    me = _guard_feature(request, FEATURE_CHAT)
    if not isinstance(me, Employee):
        return me
    title = (request.POST.get('title') or '').strip() or 'Group chat'
    ids = set(int(x) for x in request.POST.getlist('members') if x.isdigit())
    ids.add(me.pk)
    emps = [
        e for e in Employee.objects.filter(pk__in=ids, status='active')
        if e.pk == me.pk or not is_blocked(e, FEATURE_CHAT)
    ]
    if len(emps) < 2:
        messages.error(
            request,
            'Pick at least one other person to start a group '
            '(restricted employees cannot be invited).',
        )
        return redirect('collab_chat')
    conv = Conversation.objects.create(kind=Conversation.KIND_GROUP, title=title, created_by=me)
    ConversationMember.objects.bulk_create([
        ConversationMember(conversation=conv, employee=e) for e in emps
    ])
    return redirect('collab_chat_room', conv_id=conv.pk)


@require_POST
@login_required
def chat_send(request, conv_id):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    if is_blocked(me, FEATURE_CHAT):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': 'Chat access restricted.'}, status=403)
        messages.error(
            request,
            'Your Chat access has been restricted by the IT/Networks team. '
            'Contact them to restore access.',
        )
        return redirect('dashboard')
    conv = get_object_or_404(Conversation, pk=conv_id, members__employee=me)
    body = (request.POST.get('body') or '').strip()
    if body:
        ChatMessage.objects.create(conversation=conv, sender=me, body=body)
        conv.save(update_fields=['updated_at'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('collab_chat_room', conv_id=conv.pk)


@require_POST
@login_required
def chat_call_start(request, conv_id):
    """Notify conversation members and open the audio/video call room."""
    me = _guard_feature(request, FEATURE_CHAT)
    if not isinstance(me, Employee):
        return me
    conv = get_object_or_404(Conversation, pk=conv_id, members__employee=me)
    audio_only = (request.POST.get('mode') or 'audio') == 'audio'
    kind = 'audio' if audio_only else 'video'
    ChatMessage.objects.create(
        conversation=conv, sender=me,
        body=f'{me.full_name} started a {kind} call. Click "Call" to join.',
    )
    conv.save(update_fields=['updated_at'])
    url = reverse('collab_call_room', args=[conv.pk])
    return redirect(url + ('?audio=1' if audio_only else ''))


@require_POST
@login_required
def chat_call_user(request):
    """Start (or reuse) a 1:1 conversation with someone and open a call."""
    me = _guard_feature(request, FEATURE_CHAT)
    if not isinstance(me, Employee):
        return me
    other = get_object_or_404(
        Employee.objects.filter(status='active'),
        pk=request.POST.get('employee') or 0,
    )
    if other.pk == me.pk:
        messages.error(request, 'You cannot call yourself.')
        return redirect('collab_chat')
    if is_blocked(other, FEATURE_CHAT):
        messages.error(
            request,
            f'{other.full_name}\'s Chat access is restricted by the IT/Networks team.',
        )
        return redirect('collab_chat')
    conv = (Conversation.objects
            .filter(kind=Conversation.KIND_DIRECT, members__employee=me)
            .filter(members__employee=other)
            .first())
    if conv is None:
        conv = Conversation.objects.create(kind=Conversation.KIND_DIRECT, created_by=me)
        ConversationMember.objects.create(conversation=conv, employee=me)
        ConversationMember.objects.create(conversation=conv, employee=other)
    audio_only = (request.POST.get('mode') or 'video') == 'audio'
    kind = 'audio' if audio_only else 'video'
    ChatMessage.objects.create(
        conversation=conv, sender=me,
        body=f'{me.full_name} started a {kind} call. Click "Call" to join.',
    )
    conv.save(update_fields=['updated_at'])
    url = reverse('collab_call_room', args=[conv.pk])
    return redirect(url + ('?audio=1' if audio_only else ''))


@login_required
def chat_call_room(request, conv_id):
    me = _guard_feature(request, FEATURE_CHAT)
    if not isinstance(me, Employee):
        return me
    conv = get_object_or_404(Conversation, pk=conv_id, members__employee=me)
    return _call_page(
        request,
        room=conv.call_room,
        title=conv.display_title(me),
        back_url=reverse('collab_chat_room', args=[conv.pk]),
        audio_only=request.GET.get('audio') == '1',
    )


@login_required
def meeting_join(request, pk):
    me = _guard_feature(request, FEATURE_MEETINGS)
    if not isinstance(me, Employee):
        return me
    meeting = get_object_or_404(Meeting, pk=pk)
    is_attendee = meeting.attendees.filter(employee=me).exists()
    if not is_attendee and meeting.organizer_id != me.pk and not request.user.is_superuser:
        messages.error(request, 'You do not have access to this meeting.')
        return redirect('collab_meetings')
    return _call_page(
        request,
        room=meeting.room,
        title=meeting.title,
        back_url=reverse('collab_meeting_detail', args=[meeting.pk]),
        audio_only=request.GET.get('audio') == '1',
    )


def _call_page(request, room, title, back_url, audio_only=False):
    me = _me(request)
    return render(request, 'collab/join.html', {
        'room': room,
        'call_title': title,
        'back_url': back_url,
        'audio_only': audio_only,
        'display_name': me.full_name if me else request.user.username,
        'collab_tab': 'chat',
    })


@login_required
def chat_messages_json(request, conv_id):
    me = _require_me(request)
    if me is None:
        return JsonResponse({'messages': []})
    if is_blocked(me, FEATURE_CHAT):
        return JsonResponse({'ok': False, 'error': 'Chat access restricted.'}, status=403)
    conv = get_object_or_404(Conversation, pk=conv_id, members__employee=me)
    qs = conv.messages.select_related('sender').order_by('created_at')
    after = request.GET.get('after')
    if after and after.isdigit():
        qs = qs.filter(id__gt=int(after))
    data = [{
        'id': m.pk,
        'sender': m.sender.full_name if m.sender else 'Unknown',
        'sender_id': m.sender_id,
        'body': m.body,
        'time': timezone.localtime(m.created_at).strftime('%b %d, %H:%M'),
        'mine': m.sender_id == me.pk,
    } for m in qs]
    return JsonResponse({'messages': data})


# ---------------------------------------------------------------------------
# Meetings (Teams-like, Jitsi video)
# ---------------------------------------------------------------------------

@login_required
def meeting_list(request):
    me = _guard_feature(request, FEATURE_MEETINGS)
    if not isinstance(me, Employee):
        return me
    now = timezone.now()
    invited = Meeting.objects.filter(attendees__employee=me).distinct()
    upcoming = invited.filter(start_at__gte=now).order_by('start_at')
    past = invited.filter(start_at__lt=now).order_by('-start_at')[:20]
    organized = Meeting.objects.filter(organizer=me).order_by('-start_at')[:20]
    return render(request, 'collab/meeting_list.html', {
        'upcoming': upcoming, 'past': past, 'organized': organized,
        'collab_tab': 'meetings', 'now': now,
    })


def _parse_dt(value):
    dt = parse_datetime(value or '')
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


@login_required
def meeting_create(request):
    me = _guard_feature(request, FEATURE_MEETINGS)
    if not isinstance(me, Employee):
        return me
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        agenda = (request.POST.get('agenda') or '').strip()
        start_dt = _parse_dt(request.POST.get('start_at'))
        end_dt = _parse_dt(request.POST.get('end_at'))
        ids = set(int(x) for x in request.POST.getlist('attendees') if x.isdigit())
        ids.add(me.pk)

        if not title or not start_dt or not end_dt:
            messages.error(request, 'Title, start and end time are required.')
        elif end_dt <= start_dt:
            messages.error(request, 'End time must be after the start time.')
        else:
            attendees = [
                e for e in Employee.objects.filter(pk__in=ids, status='active')
                if e.pk == me.pk or not is_blocked(e, FEATURE_MEETINGS)
            ]
            room = 'CoreCloud-' + get_random_string(10)
            meeting = Meeting.objects.create(
                title=title, agenda=agenda, organizer=me,
                start_at=start_dt, end_at=end_dt, room=room,
            )
            from hr_modules.notify import notify
            for emp in attendees:
                MeetingAttendee.objects.create(meeting=meeting, employee=emp)
                if emp.pk != me.pk:
                    notify(
                        emp,
                        f'Meeting invite: {title}',
                        f'{me.full_name} invited you to "{title}" on '
                        f'{timezone.localtime(start_dt):%b %d, %Y %H:%M} UTC.',
                        'info',
                        f'/collab/meetings/{meeting.pk}/',
                    )
            messages.success(request, 'Meeting scheduled.')
            return redirect('collab_meeting_detail', pk=meeting.pk)

    return render(request, 'collab/meeting_form.html', {
        'employees': accessible_employees(FEATURE_MEETINGS, exclude=me),
        'collab_tab': 'meetings',
    })


@login_required
def meeting_detail(request, pk):
    me = _guard_feature(request, FEATURE_MEETINGS)
    if not isinstance(me, Employee):
        return me
    meeting = get_object_or_404(Meeting, pk=pk)
    is_attendee = meeting.attendees.filter(employee=me).exists()
    if not is_attendee and meeting.organizer_id != me.pk and not request.user.is_superuser:
        messages.error(request, 'You do not have access to this meeting.')
        return redirect('collab_meetings')
    my_attendee = meeting.attendees.filter(employee=me).first()
    return render(request, 'collab/meeting_detail.html', {
        'meeting': meeting, 'my_attendee': my_attendee,
        'is_organizer': meeting.organizer_id == me.pk,
        'collab_tab': 'meetings',
    })


@require_POST
@login_required
def meeting_respond(request, pk):
    me = _guard_feature(request, FEATURE_MEETINGS)
    if not isinstance(me, Employee):
        return me
    meeting = get_object_or_404(Meeting, pk=pk)
    attendee = get_object_or_404(MeetingAttendee, meeting=meeting, employee=me)
    new_status = request.POST.get('status')
    if new_status in dict(MeetingAttendee.STATUS_CHOICES):
        attendee.status = new_status
        attendee.save(update_fields=['status'])
        messages.success(request, f'You {new_status} the meeting.')
    return redirect('collab_meeting_detail', pk=meeting.pk)
