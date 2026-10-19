from datetime import timedelta
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from employees.audit import log_audit
from employees.decorators import permission_required
from employees.models import AuditLog

from .models import Alert, DetectionRule, Incident, IncidentNote, ResponseAction, SOCIPEntry

SEVERITY_BADGE = {
    'critical': 'danger', 'high': 'warning', 'medium': 'primary',
    'low': 'info', 'info': 'secondary',
}
STATUS_BADGE = {
    'new': 'danger', 'acknowledged': 'warning', 'closed': 'secondary',
    'open': 'danger', 'triaging': 'warning', 'contained': 'info',
    'resolved': 'success',
}


def _kpi_context():
    now = timezone.now()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    alerts_24h = (Alert.objects.filter(first_seen__gte=day_ago)
                  .values('severity').annotate(n=Count('id')))
    sev_map = {row['severity']: row['n'] for row in alerts_24h}
    new_alerts = Alert.objects.filter(status='new').count()
    open_incidents = Incident.objects.filter(status__in=('open', 'triaging', 'contained')).count()
    events_24h = AuditLog.objects.filter(timestamp__gte=day_ago).count()
    mttr_minutes = None
    resolved = Incident.objects.filter(closed_at__isnull=False)
    if resolved.exists():
        deltas = [(i.closed_at - i.created_at).total_seconds() / 60 for i in resolved]
        mttr_minutes = round(sum(deltas) / len(deltas), 1)
    acknowledged = Alert.objects.filter(status='acknowledged')
    mtta_minutes = None
    if acknowledged.exists():
        deltas = [(a.last_seen - a.first_seen).total_seconds() / 60 for a in acknowledged]
        mtta_minutes = round(sum(deltas) / len(deltas), 1)
    return {
        'sev_map': sev_map,
        'new_alerts': new_alerts,
        'open_incidents': open_incidents,
        'events_24h': events_24h,
        'alerts_week': Alert.objects.filter(first_seen__gte=week_ago).count(),
        'mttr_minutes': mttr_minutes,
        'mtta_minutes': mtta_minutes,
        'SEVERITY_BADGE': SEVERITY_BADGE,
        'STATUS_BADGE': STATUS_BADGE,
    }


@login_required
@permission_required('view_soc')
def dashboard(request):
    ctx = _kpi_context()
    ctx['recent_alerts'] = Alert.objects.select_related('rule', 'incident')[:10]
    ctx['open_incidents_list'] = (
        Incident.objects.filter(status__in=('open', 'triaging', 'contained'))[:8])
    return render(request, 'soc/dashboard.html', ctx)


@login_required
@permission_required('view_soc')
def api_stats(request):
    now = timezone.now()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    # Hourly event volume by severity (last 24h)
    hours = list(range(23, -1, -1))
    labels, series = [], {s: [] for s, _ in [
        ('critical', 1), ('high', 1), ('medium', 1), ('low', 1), ('info', 1)]}
    base = day_ago.replace(minute=0, second=0, microsecond=0)
    for h in hours:
        start = base + timedelta(hours=h)
        end = start + timedelta(hours=1)
        labels.append(start.strftime('%H:00'))
        bucket = {row['severity']: row['n'] for row in
                  (AuditLog.objects.filter(timestamp__gte=start, timestamp__lt=end)
                   .values('severity').annotate(n=Count('id')))}
        for sev in series:
            series[sev].append(bucket.get(sev, 0))

    rule_rows = (Alert.objects.filter(first_seen__gte=week_ago)
                 .values('rule__name').annotate(n=Count('id')).order_by('-n')[:8])
    top_rules = {
        'labels': [row['rule__name'] for row in rule_rows],
        'counts': [row['n'] for row in rule_rows],
    }

    ip_rows = (AuditLog.objects.filter(timestamp__gte=day_ago, ip_address__isnull=False)
               .exclude(ip_address='')
               .values('ip_address').annotate(n=Count('id')).order_by('-n')[:8])
    top_ips = {'labels': [row['ip_address'] for row in ip_rows],
               'counts': [row['n'] for row in ip_rows]}

    actor_rows = (AuditLog.objects.filter(timestamp__gte=day_ago, user__isnull=False)
                  .values('user__username').annotate(n=Count('id')).order_by('-n')[:8])
    top_actors = {'labels': [row['user__username'] for row in actor_rows],
                  'counts': [row['n'] for row in actor_rows]}

    action_rows = (AuditLog.objects.filter(timestamp__gte=week_ago)
                   .values('action').annotate(n=Count('id')).order_by('-n'))
    action_mix = {'labels': [row['action'] for row in action_rows],
                  'counts': [row['n'] for row in action_rows]}

    return JsonResponse({
        'volume': {'labels': labels, 'series': series},
        'top_rules': top_rules,
        'top_ips': top_ips,
        'top_actors': top_actors,
        'action_mix': action_mix,
    })


@login_required
@permission_required('view_soc')
def api_live_events(request):
    since = request.GET.get('since')
    events = AuditLog.objects.all().order_by('-timestamp')[:25]
    if since:
        events = AuditLog.objects.filter(timestamp__gt=since).order_by('timestamp')[:25]
    return JsonResponse({'events': [{
        'id': e.pk,
        'time': e.timestamp.strftime('%H:%M:%S'),
        'timestamp': e.timestamp.isoformat(),
        'user': getattr(e.user, 'username', 'system'),
        'action': e.action,
        'severity': e.severity or 'info',
        'description': (e.description or '')[:160],
        'ip': e.ip_address or '-',
    } for e in events]})


@login_required
@permission_required('view_soc')
def event_list(request):
    events = AuditLog.objects.select_related('user')
    q = request.GET.get('search', '').strip()
    action = request.GET.get('action', '')
    severity = request.GET.get('severity', '')
    category = request.GET.get('category', '')
    if q:
        events = events.filter(
            Q(description__icontains=q) | Q(object_id__icontains=q)
            | Q(user__username__icontains=q) | Q(ip_address__icontains=q))
    if action:
        events = events.filter(action=action)
    if severity:
        events = events.filter(severity=severity)
    if category:
        events = events.filter(category=category)
    from django.core.paginator import Paginator
    page_obj = Paginator(events, 50).get_page(request.GET.get('page'))
    return render(request, 'soc/event_list.html', {
        'page_obj': page_obj, 'logs': page_obj,
        'search': q, 'action_filter': action,
        'severity_filter': severity, 'category_filter': category,
        'ACTION_CHOICES': AuditLog.ACTION_CHOICES,
        'SEVERITY_CHOICES': AuditLog.SEVERITY_CHOICES,
        'CATEGORY_CHOICES': AuditLog.CATEGORY_CHOICES,
        'SEVERITY_BADGE': SEVERITY_BADGE,
    })


@login_required
@permission_required('view_soc')
def alert_list(request):
    alerts = Alert.objects.select_related('rule', 'incident', 'assignee')
    status = request.GET.get('status', '')
    severity = request.GET.get('severity', '')
    q = request.GET.get('search', '').strip()
    if status:
        alerts = alerts.filter(status=status)
    if severity:
        alerts = alerts.filter(severity=severity)
    if q:
        alerts = alerts.filter(Q(title__icontains=q) | Q(detail__icontains=q)
                               | Q(subject_username__icontains=q))
    from django.core.paginator import Paginator
    page_obj = Paginator(alerts, 25).get_page(request.GET.get('page'))
    return render(request, 'soc/alert_list.html', {
        'page_obj': page_obj, 'alerts': page_obj,
        'status_filter': status, 'severity_filter': severity, 'search': q,
        'STATUS_BADGE': STATUS_BADGE, 'SEVERITY_BADGE': SEVERITY_BADGE,
    })


@login_required
@permission_required('view_soc')
def alert_detail(request, pk):
    alert = get_object_or_404(
        Alert.objects.select_related('rule', 'incident', 'event', 'assignee'), pk=pk)
    return render(request, 'soc/alert_detail.html', {
        'alert': alert,
        'actions': alert.actions.all(),
        'STATUS_BADGE': STATUS_BADGE, 'SEVERITY_BADGE': SEVERITY_BADGE,
    })


@login_required
@permission_required('respond_soc')
@require_POST
def alert_action(request, pk):
    alert = get_object_or_404(Alert, pk=pk)
    action = request.POST.get('action', '')
    if action == 'ack':
        alert.status = 'acknowledged'
        alert.assignee = request.user
        alert.save(update_fields=['status', 'assignee'])
        messages.success(request, 'Alert acknowledged.')
    elif action == 'close':
        alert.status = 'closed'
        alert.assignee = request.user
        alert.save(update_fields=['status', 'assignee'])
        ResponseAction.objects.create(
            alert=alert, action='notify', actor=request.user.username,
            result='Alert closed manually', params={})
        messages.success(request, 'Alert closed.')
    elif action == 'escalate':
        incident = Incident.objects.create(
            title=alert.title, detail=alert.detail, severity=alert.severity,
            status='open', team='networks')
        IncidentNote.objects.create(
            incident=incident, author=request.user, kind='status_change',
            body=f'Incident created from alert #{alert.pk} ({alert.rule.name}).')
        alert.incident = incident
        alert.status = 'acknowledged'
        alert.assignee = request.user
        alert.save(update_fields=['incident', 'status', 'assignee'])
        log_audit(
            user=request.user, action='update', model_name='Incident',
            object_id=incident.pk,
            description=f'Incident #{incident.pk} created from alert #{alert.pk}',
            request=request, category='access', severity='medium',
        )
        messages.success(request, f'Escalated to incident #{incident.pk}.')
    elif action == 'lock':
        from .playbooks import lock_account
        employee = _alert_employee(alert)
        if employee is None:
            messages.error(request, 'No employee matches this alert subject.')
        else:
            lock_account(alert, employee)
            log_audit(
                user=request.user, action='response', model_name='Employee',
                object_id=employee.employee_id,
                description=f'Manual SOC lock of {employee.employee_id} (alert #{alert.pk})',
                request=request, category='auth', severity='high',
            )
            messages.success(request, f'Locked {employee.employee_id} and revoked sessions.')
    elif action == 'unlock':
        from employees.lockout import clear_login_lock
        employee = _alert_employee(alert)
        if employee is None:
            messages.error(request, 'No employee matches this alert subject.')
        elif not (employee.is_login_locked or employee.failed_login_attempts):
            messages.info(request, f'{employee.employee_id} is not locked.')
        else:
            clear_login_lock(employee)
            ResponseAction.objects.create(
                alert=alert, action='unlock_account', actor=request.user.username,
                result=f'Unlocked {employee.employee_id}', params={})
            log_audit(
                user=request.user, action='unlock', model_name='Employee',
                object_id=employee.employee_id,
                description=f'Manual SOC unlock of {employee.employee_id} (alert #{alert.pk})',
                request=request, category='auth', severity='medium', outcome='success',
            )
            messages.success(request, f'Unlocked {employee.employee_id}.')
    elif action == 'blacklist_ip':
        ip = (request.POST.get('ip') or '').strip()
        if not ip:
            messages.error(request, 'No IP address on this alert to blacklist.')
        else:
            SOCIPEntry.objects.update_or_create(
                ip_address=ip,
                defaults={'list_type': 'blacklist',
                          'reason': f'Blacklisted from alert #{alert.pk}',
                          'added_by': request.user})
            log_audit(
                user=request.user, action='update', model_name='SOCIPEntry',
                object_id=ip,
                description=f'IP {ip} blacklisted from alert #{alert.pk}',
                request=request, category='config', severity='high',
            )
            messages.success(request, f'IP {ip} blacklisted. Future activity from it will raise alerts instantly.')
    return redirect('soc_alert_detail', pk=pk)


def _alert_employee(alert):
    if not alert.subject_username:
        return None
    from employees.models import Employee
    return (Employee.objects.filter(employee_id=alert.subject_username)
            .select_related('user').first()
            or Employee.objects.filter(user__username=alert.subject_username)
            .select_related('user').first())


@login_required
@permission_required('view_soc')
def incident_list(request):
    incidents = Incident.objects.select_related('assignee')
    status = request.GET.get('status', '')
    q = request.GET.get('search', '').strip()
    if status:
        incidents = incidents.filter(status=status)
    if q:
        incidents = incidents.filter(Q(title__icontains=q) | Q(detail__icontains=q))
    from django.core.paginator import Paginator
    page_obj = Paginator(incidents, 25).get_page(request.GET.get('page'))
    return render(request, 'soc/incident_list.html', {
        'page_obj': page_obj, 'incidents': page_obj,
        'status_filter': status, 'search': q,
        'STATUS_BADGE': STATUS_BADGE, 'SEVERITY_BADGE': SEVERITY_BADGE,
    })


@login_required
@permission_required('view_soc')
def incident_detail(request, pk):
    incident = get_object_or_404(Incident.objects.select_related('assignee'), pk=pk)
    from django.contrib.auth.models import User
    from employees.models import Employee
    assignable_ids = set(emp.user_id for emp in Employee.objects.filter(
        Q(support_team__in=('networks', 'software', 'hardware'))
        | Q(is_it_manager=True)).exclude(user=None))
    assignable_users = User.objects.filter(
        Q(pk__in=assignable_ids) | Q(is_superuser=True)).order_by('username')
    return render(request, 'soc/incident_detail.html', {
        'incident': incident,
        'notes': incident.notes.select_related('author'),
        'linked_alerts': incident.alerts.select_related('rule'),
        'actions': incident.actions.all(),
        'assignable_users': assignable_users,
        'STATUS_BADGE': STATUS_BADGE, 'SEVERITY_BADGE': SEVERITY_BADGE,
    })


@login_required
@permission_required('respond_soc')
@require_POST
def incident_update(request, pk):
    incident = get_object_or_404(Incident, pk=pk)
    new_status = request.POST.get('status', '')
    if new_status and new_status in dict(Incident.STATUS_CHOICES):
        old = incident.status
        incident.status = new_status
        if new_status in ('resolved', 'closed'):
            incident.closed_at = timezone.now()
        incident.save()
        IncidentNote.objects.create(
            incident=incident, author=request.user, kind='status_change',
            body=f'{request.user.username} changed status: {old} → {new_status}')
        log_audit(
            user=request.user, action='update', model_name='Incident',
            object_id=incident.pk,
            description=f'Incident #{incident.pk} status {old} → {new_status}',
            request=request, category='access', severity='medium',
        )
        messages.success(request, f'Incident #{incident.pk} is now {new_status}.')
    note = (request.POST.get('note') or '').strip()
    if note:
        IncidentNote.objects.create(
            incident=incident, author=request.user, kind='comment', body=note[:4000])
    team = request.POST.get('team', '')
    if team in dict(Incident.TEAM_CHOICES):
        incident.team = team
        incident.save(update_fields=['team'])
    assignee_id = request.POST.get('assignee')
    if assignee_id:
        from django.contrib.auth.models import User
        user = User.objects.filter(pk=assignee_id).first()
        if user:
            incident.assignee = user
            incident.save(update_fields=['assignee'])
    return redirect('soc_incident_detail', pk=pk)


@login_required
@permission_required('manage_soc')
def rule_list(request):
    rules = DetectionRule.objects.all()
    return render(request, 'soc/rule_list.html', {
        'rules': rules, 'SEVERITY_BADGE': SEVERITY_BADGE,
    })


@login_required
@permission_required('manage_soc')
@require_POST
def rule_toggle(request, pk):
    rule = get_object_or_404(DetectionRule, pk=pk)
    field = request.POST.get('field', 'enabled')
    if field in ('enabled', 'auto_response'):
        setattr(rule, field, not getattr(rule, field))
        rule.save(update_fields=[field])
        log_audit(
            user=request.user, action='update', model_name='DetectionRule',
            object_id=rule.key,
            description=f'Set {rule.key}.{field}={getattr(rule, field)}',
            request=request, category='config', severity='medium',
        )
        messages.success(request, f'{rule.name}: {field} is now {getattr(rule, field)}.')
    return redirect('soc_rule_list')


@login_required
@permission_required('manage_soc')
def ip_list(request):
    entries = SOCIPEntry.objects.select_related('added_by')
    q = request.GET.get('search', '').strip()
    if q:
        entries = entries.filter(ip_address__icontains=q)
    from django.core.paginator import Paginator
    page_obj = Paginator(entries, 50).get_page(request.GET.get('page'))
    return render(request, 'soc/ip_list.html', {
        'page_obj': page_obj, 'entries': page_obj, 'search': q,
    })


@login_required
@permission_required('manage_soc')
@require_POST
def ip_add(request):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_ipv46_address
    ip = (request.POST.get('ip_address') or '').strip()
    list_type = request.POST.get('list_type', 'whitelist')
    reason = (request.POST.get('reason') or '').strip()
    if list_type not in ('whitelist', 'blacklist'):
        list_type = 'whitelist'
    try:
        validate_ipv46_address(ip)
    except ValidationError:
        messages.error(request, f'"{ip}" is not a valid IP address.')
        return redirect('soc_ip_list')
    entry, created = SOCIPEntry.objects.update_or_create(
        ip_address=ip,
        defaults={'list_type': list_type, 'reason': reason, 'added_by': request.user})
    log_audit(
        user=request.user, action='update', model_name='SOCIPEntry',
        object_id=ip,
        description=f'IP {ip} added to {entry.get_list_type_display()}'
                    + (f' ({reason})' if reason else ''),
        request=request, category='config', severity='medium',
    )
    messages.success(request, f'IP {ip} {"added to" if created else "moved to"} '
                              f'{entry.get_list_type_display()}.')
    return redirect('soc_ip_list')


@login_required
@permission_required('manage_soc')
@require_POST
def ip_remove(request, pk):
    entry = get_object_or_404(SOCIPEntry, pk=pk)
    ip, list_type = entry.ip_address, entry.get_list_type_display()
    entry.delete()
    log_audit(
        user=request.user, action='update', model_name='SOCIPEntry',
        object_id=ip,
        description=f'IP {ip} removed from {list_type}',
        request=request, category='config', severity='medium',
    )
    messages.success(request, f'IP {ip} removed from {list_type}.')
    return redirect('soc_ip_list')


def cron_scan(request):
    """Vercel cron endpoint: /cron/soc/ re-runs the 24h detection scan.

    Vercel calls this with ``Authorization: Bearer $CRON_SECRET``; locally you
    can use ``/cron/soc/?secret=<SOC_CRON_SECRET>``.
    """
    import hmac
    from django.conf import settings
    secret = (getattr(settings, 'SOC_CRON_SECRET', '')
              or os.environ.get('CRON_SECRET', ''))
    provided = request.GET.get('secret') or request.headers.get('Authorization', '')
    ok = bool(secret) and (
        hmac.compare_digest(provided, secret)
        or hmac.compare_digest(provided, f'Bearer {secret}'))
    if not ok:
        return JsonResponse({'detail': 'forbidden'}, status=403)
    from .engine import run_scan
    from .management.commands.run_soc_rules import seed_rules
    seed_rules()
    scanned = run_scan(hours=24)
    return JsonResponse({'status': 'ok', 'scanned': scanned})
