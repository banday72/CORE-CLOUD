"""Views for the internal collaboration app (Mail, Chat, Meetings)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from employees.models import Department, Employee

from .models import (
    ChatMessage, Conversation, ConversationMember,
    MailMessage, MailRecipient, Meeting, MeetingAttendee,
)


def _me(request):
    return getattr(request.user, 'employee', None)


def _require_me(request):
    """Return the current Employee or None (after queueing an error message)."""
    me = _me(request)
    if me is None:
        messages.error(request, 'No employee profile is linked to this account.')
    return me


def _active_employees(exclude=None):
    qs = Employee.objects.filter(status='active').select_related('department').order_by('first_name', 'last_name')
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


# ---------------------------------------------------------------------------
# Mail (Outlook-like)
# ---------------------------------------------------------------------------

@login_required
def mail_inbox(request):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
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
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    mails = (MailMessage.objects
             .filter(sender=me)
             .prefetch_related('recipients__employee'))
    return render(request, 'collab/mail_sent.html', {
        'mails': mails, 'collab_tab': 'mail_sent',
    })


@login_required
def mail_compose(request):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')

    if request.method == 'POST':
        subject = (request.POST.get('subject') or '').strip()
        body = (request.POST.get('body') or '').strip()
        recipient_ids = set(int(x) for x in request.POST.getlist('recipients') if x.isdigit())

        dept_id = request.POST.get('department')
        if dept_id and dept_id.isdigit():
            recipient_ids |= set(
                Employee.objects.filter(status='active', department_id=int(dept_id))
                .values_list('pk', flat=True)
            )
        if request.POST.get('all_active'):
            recipient_ids |= set(
                Employee.objects.filter(status='active').values_list('pk', flat=True)
            )

        recipient_ids.discard(me.pk)

        if not subject or not body or not recipient_ids:
            messages.error(request, 'Subject, message and at least one recipient are required.')
        else:
            recipients = list(Employee.objects.filter(pk__in=recipient_ids, status='active'))
            mail = MailMessage.objects.create(sender=me, subject=subject, body=body)
            MailRecipient.objects.bulk_create([
                MailRecipient(mail=mail, employee=emp) for emp in recipients
            ])

            try:
                from hr_modules.emails import send_ticket_email
                for emp in recipients:
                    send_ticket_email(
                        emp,
                        f'[CoreCloud Mail] {subject}',
                        f'You have a new internal message from {me.full_name}.\n\n'
                        f'{body}\n\n— Sent via CoreCloud internal mail.',
                    )
            except Exception:
                pass

            messages.success(request, f'Message sent to {len(recipients)} recipient(s).')
            return redirect('collab_mail_sent')

    return render(request, 'collab/mail_compose.html', {
        'employees': _active_employees(me),
        'departments': Department.objects.all(),
        'collab_tab': 'mail_compose',
    })


@login_required
def mail_detail(request, pk):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    rec = get_object_or_404(
        MailRecipient.objects.select_related('mail', 'mail__sender'),
        pk=pk, employee=me, is_deleted=False,
    )
    if not rec.is_read:
        rec.is_read = True
        rec.read_at = timezone.now()
        rec.save(update_fields=['is_read', 'read_at'])
    return render(request, 'collab/mail_detail.html', {
        'rec': rec, 'mail': rec.mail, 'collab_tab': 'mail_inbox',
    })


@require_POST
@login_required
def mail_delete(request, pk):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
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
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')

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
        'employees': _active_employees(me),
        'collab_tab': 'chat',
    })


@require_POST
@login_required
def chat_start_direct(request):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    other = get_object_or_404(Employee, pk=request.POST.get('employee') or 0)
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
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    title = (request.POST.get('title') or '').strip() or 'Group chat'
    ids = set(int(x) for x in request.POST.getlist('members') if x.isdigit())
    ids.add(me.pk)
    emps = list(Employee.objects.filter(pk__in=ids))
    if len(emps) < 2:
        messages.error(request, 'Pick at least one other person to start a group.')
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
    conv = get_object_or_404(Conversation, pk=conv_id, members__employee=me)
    body = (request.POST.get('body') or '').strip()
    if body:
        ChatMessage.objects.create(conversation=conv, sender=me, body=body)
        conv.save(update_fields=['updated_at'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('collab_chat_room', conv_id=conv.pk)


@login_required
def chat_messages_json(request, conv_id):
    me = _require_me(request)
    if me is None:
        return JsonResponse({'messages': []})
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
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
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
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
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
            room = 'CoreCloud-' + get_random_string(10)
            meeting = Meeting.objects.create(
                title=title, agenda=agenda, organizer=me,
                start_at=start_dt, end_at=end_dt, room=room,
            )
            from hr_modules.notify import notify
            for emp in Employee.objects.filter(pk__in=ids):
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
        'employees': _active_employees(me), 'collab_tab': 'meetings',
    })


@login_required
def meeting_detail(request, pk):
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
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
    me = _require_me(request)
    if me is None:
        return redirect('dashboard')
    meeting = get_object_or_404(Meeting, pk=pk)
    attendee = get_object_or_404(MeetingAttendee, meeting=meeting, employee=me)
    new_status = request.POST.get('status')
    if new_status in dict(MeetingAttendee.STATUS_CHOICES):
        attendee.status = new_status
        attendee.save(update_fields=['status'])
        messages.success(request, f'You {new_status} the meeting.')
    return redirect('collab_meeting_detail', pk=meeting.pk)
