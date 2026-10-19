"""Automated response playbooks.

Run when a critical/high auto-response alert opens: lock the target account,
revoke its sessions, open a password-reset ticket and notify the networks
team.  Every step is recorded as a ``ResponseAction`` (actor='system').
"""

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('soc')


def _record(alert, action, params, result, success=True):
    from .models import ResponseAction
    return ResponseAction.objects.create(
        alert=alert, incident=alert.incident, action=action,
        params=params, result=result, success=success, actor='system',
    )


def _find_employee(username):
    from employees.models import Employee
    if not username:
        return None
    return (Employee.objects.filter(employee_id=username).select_related('user').first()
            or Employee.objects.filter(user__username=username).select_related('user').first())


def lock_account(alert, employee):
    from employees.lockout import LOCKOUT_MINUTES, open_password_reset_ticket
    from employees.audit import log_audit
    if employee.is_login_locked:
        _record(alert, 'lock_account', {'employee': employee.employee_id},
                'Already locked', success=True)
        return True
    employee.login_locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
    employee.failed_login_attempts = 0
    employee.save(update_fields=['login_locked_until', 'failed_login_attempts'])
    log_audit(
        user=None, action='lockout', model_name='Employee',
        object_id=employee.employee_id,
        description=f'SOC auto-response locked the account (alert #{alert.pk})',
        severity='critical', outcome='failure', category='auth',
    )
    _record(alert, 'lock_account', {'employee': employee.employee_id, 'minutes': LOCKOUT_MINUTES},
            f'Locked until {employee.login_locked_until:%Y-%m-%d %H:%M} UTC')
    if employee.user:
        revoke_sessions(alert, employee.user)
    open_password_reset_ticket(employee)
    _record(alert, 'open_ticket', {'employee': employee.employee_id},
            'Password reset ticket ensured')
    return True


def revoke_sessions(alert, user):
    revoked = 0
    now = timezone.now()
    for session in Session.objects.filter(expire_date__gte=now):
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.pk):
            session.delete()
            revoked += 1
    _record(alert, 'revoke_sessions', {'user': user.username},
            f'Deleted {revoked} active session(s)')
    return revoked


def notify(alert):
    from hr_modules.views import notify_team
    notify_team(
        'networks',
        f'SOC alert: {alert.title}',
        f'{alert.detail}\nRule: {alert.rule.name} ({alert.get_severity_display()}). '
        f'Review under Security Operations → Alerts.',
        'warning',
        f'/soc/alerts/?id={alert.pk}',
    )
    _record(alert, 'notify', {'team': 'networks'}, 'Networks team notified')


def run_playbooks(alert):
    """Execute response steps for a freshly opened alert."""
    if not settings.SOC_AUTO_RESPONSE:
        return []
    if alert.actions.filter(actor='system').exists():
        return []
    results = []
    employee = _find_employee(alert.subject_username)
    notify(alert)
    if employee is not None:
        results.append(lock_account(alert, employee))
    else:
        _record(alert, 'lock_account', {'username': alert.subject_username},
                'No matching employee found for auto-lock', success=False)
    logger.info('Playbooks finished for alert %s', alert.pk)
    return results
