"""SOC detection engine.

Evaluates audit events against ``DetectionRule`` rows and opens (or
de-duplicates) ``Alert`` rows.  Rules are window/threshold based; each check
queries the audit trail for activity inside the rule window and fires when the
threshold is reached.  Repeated firings with the same fingerprint increment the
existing open alert instead of creating noise.
"""

import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('soc')

AUTH_ACTIONS = {'login', 'login_failed', 'face_login'}


def _fingerprint(rule_key, *parts):
    raw = '|'.join([rule_key] + [str(p or '') for p in parts])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]


def _rule(key):
    from .models import DetectionRule
    try:
        return DetectionRule.objects.get(key=key, enabled=True)
    except DetectionRule.DoesNotExist:
        return None


def open_alert(rule, fingerprint, title, detail, event=None, subject_username=''):
    """Create an alert or increment the matching open one. Returns the alert."""
    from .models import Alert
    now = event.timestamp if event else timezone.now()
    existing = Alert.objects.filter(
        rule=rule, fingerprint=fingerprint, status='new').order_by('-last_seen').first()
    if existing:
        existing.count += 1
        existing.last_seen = now
        if event and not existing.event_id:
            existing.event = event
        existing.save(update_fields=['count', 'last_seen'] + (['event'] if event and not existing.event_id else []))
        return existing
    alert = Alert.objects.create(
        rule=rule, title=title[:200], detail=detail, severity=rule.severity,
        fingerprint=fingerprint, subject_username=subject_username,
        event=event, first_seen=now, last_seen=now,
    )
    logger.info('ALERT opened: %s [%s] %s', rule.key, rule.severity, title)
    _run_playbooks(alert)
    return alert


def _run_playbooks(alert):
    if not alert.rule.auto_response:
        return
    if not getattr(settings, 'SOC_AUTO_RESPONSE', True):
        return
    try:
        from .playbooks import run_playbooks
        run_playbooks(alert)
    except Exception:
        logger.exception('Playbook execution failed for alert %s', alert.pk)


def evaluate_event(event):
    """Run every rule check against a freshly written audit event."""
    from .models import DetectionRule
    if not DetectionRule.objects.filter(enabled=True).exists():
        return
    for check in (
        check_brute_force,
        check_credential_stuffing,
        check_account_lockout,
        check_suspicious_ip,
        check_mass_export,
        check_off_hours_admin,
        check_privilege_change,
        check_ip_switch,
        check_locked_attempt,
    ):
        try:
            check(event)
        except Exception:
            logger.exception('Rule check %s failed', check.__name__)


def run_scan(hours=24):
    """Backstop scan: re-evaluate recent events (catches drift/time windows)."""
    from employees.models import AuditLog
    since = timezone.now() - timedelta(hours=hours)
    events = AuditLog.objects.filter(timestamp__gte=since).order_by('timestamp')
    count = 0
    for event in events:
        evaluate_event(event)
        count += 1
    return count


def check_brute_force(event):
    if event.action != 'login_failed' or not event.user:
        return
    rule = _rule('brute_force')
    if not rule:
        return
    from employees.models import AuditLog
    since = timezone.now() - timedelta(minutes=rule.window_minutes)
    failures = AuditLog.objects.filter(
        action='login_failed', user=event.user, timestamp__gte=since).count()
    if failures >= rule.threshold:
        open_alert(
            rule, _fingerprint('brute_force', event.user.username),
            f'Brute force on {event.user.username}',
            f'{failures} failed login attempts for {event.user.username} '
            f'in the last {rule.window_minutes} minutes.',
            event=event, subject_username=event.user.username,
        )


def check_credential_stuffing(event):
    if event.action != 'login_failed' or not event.ip_address:
        return
    rule = _rule('credential_stuffing')
    if not rule:
        return
    from django.db.models import Count
    from employees.models import AuditLog
    since = timezone.now() - timedelta(minutes=rule.window_minutes)
    per_user = (AuditLog.objects
                .filter(action='login_failed', ip_address=event.ip_address,
                        timestamp__gte=since, user__isnull=False)
                .values('user').annotate(n=Count('id')))
    total = sum(row['n'] for row in per_user)
    distinct_users = len(per_user)
    if total >= rule.threshold and distinct_users >= int(rule.params.get('min_users', 3)):
        open_alert(
            rule, _fingerprint('credential_stuffing', event.ip_address),
            f'Credential stuffing from {event.ip_address}',
            f'{total} failed logins across {distinct_users} distinct accounts '
            f'from IP {event.ip_address} in the last {rule.window_minutes} minutes.',
            event=event,
        )


def check_account_lockout(event):
    if event.action != 'lockout':
        return
    rule = _rule('account_lockout')
    if not rule:
        return
    open_alert(
        rule, _fingerprint('account_lockout', event.object_id),
        f'Account locked: {event.object_id}',
        event.description or f'Account {event.object_id} was locked.',
        event=event, subject_username=event.object_id,
    )


def check_suspicious_ip(event):
    if event.action not in AUTH_ACTIONS or not event.ip_address:
        return
    rule = _rule('suspicious_ip')
    if not rule:
        return
    from django.db.models import Count
    from employees.models import AuditLog
    since = timezone.now() - timedelta(minutes=rule.window_minutes)
    per_user = (AuditLog.objects
                .filter(action__in=AUTH_ACTIONS, ip_address=event.ip_address,
                        timestamp__gte=since, user__isnull=False)
                .values('user').annotate(n=Count('id')).distinct())
    distinct_users = len(per_user)
    if distinct_users >= rule.threshold:
        open_alert(
            rule, _fingerprint('suspicious_ip', event.ip_address),
            f'Suspicious IP {event.ip_address}',
            f'IP {event.ip_address} touched {distinct_users} distinct accounts '
            f'in the last {rule.window_minutes} minutes.',
            event=event,
        )


def check_mass_export(event):
    if event.action != 'export' or not event.user:
        return
    rule = _rule('mass_export')
    if not rule:
        return
    from employees.models import AuditLog
    since = timezone.now() - timedelta(minutes=rule.window_minutes)
    exports = AuditLog.objects.filter(
        action='export', user=event.user, timestamp__gte=since).count()
    if exports >= rule.threshold:
        open_alert(
            rule, _fingerprint('mass_export', event.user.username),
            f'Mass data export by {event.user.username}',
            f'{exports} CSV exports by {event.user.username} in the last '
            f'{rule.window_minutes} minutes.',
            event=event, subject_username=event.user.username,
        )


def check_off_hours_admin(event):
    if event.action not in ('create', 'update', 'delete', 'authorize', 'deauthorize'):
        return
    if event.category and event.category != 'access':
        return
    rule = _rule('off_hours_admin')
    if not rule or not event.user:
        return
    start = int(rule.params.get('start_hour', 6))
    end = int(rule.params.get('end_hour', 22))
    hour = event.timestamp.hour
    if start <= hour < end:
        return
    open_alert(
        rule, _fingerprint('off_hours_admin', event.user.username, event.action,
                           event.object_id, event.timestamp.strftime('%Y%m%d%H')),
        f'Off-hours change by {event.user.username}',
        f'{event.user.username} performed {event.action} on '
        f'{event.model_name}:{event.object_id} at {event.timestamp:%H:%M} UTC '
        f'(allowed window {start:02d}:00-{end:02d}:00).',
        event=event, subject_username=event.user.username,
    )


def check_privilege_change(event):
    if event.action not in ('authorize', 'deauthorize'):
        return
    rule = _rule('privilege_change')
    if not rule:
        return
    open_alert(
        rule, _fingerprint('privilege_change', event.action, event.object_id,
                           event.timestamp.strftime('%Y%m%d%H%M')),
        f'Privilege change: {event.action} {event.object_id}',
        event.description or f'{event.user} executed {event.action} on {event.object_id}.',
        event=event, subject_username=event.object_id,
    )


def check_ip_switch(event):
    if event.action != 'login' or not (event.user and event.ip_address):
        return
    rule = _rule('ip_switch')
    if not rule:
        return
    from employees.models import AuditLog
    since = timezone.now() - timedelta(minutes=rule.window_minutes)
    ips = set(AuditLog.objects
              .filter(action='login', user=event.user, timestamp__gte=since)
              .exclude(ip_address=None)
              .values_list('ip_address', flat=True))
    if len(ips) >= rule.threshold:
        open_alert(
            rule, _fingerprint('ip_switch', event.user.username),
            f'Rapid IP switch for {event.user.username}',
            f'{event.user.username} logged in from {len(ips)} distinct IPs '
            f'in the last {rule.window_minutes} minutes: {", ".join(sorted(ips))}.',
            event=event, subject_username=event.user.username,
        )


def check_locked_attempt(event):
    if event.action != 'login_failed':
        return
    if 'locked' not in (event.description or '').lower():
        return
    rule = _rule('locked_attempt')
    if not rule:
        return
    subject = event.object_id or (event.user.username if event.user else '')
    open_alert(
        rule, _fingerprint('locked_attempt', subject, event.timestamp.strftime('%Y%m%d%H')),
        f'Login attempts on locked account {subject}',
        event.description,
        event=event, subject_username=subject,
    )
