from datetime import timedelta

from django.utils import timezone

MAX_LOGIN_ATTEMPTS = 7
LOCKOUT_MINUTES = 30
LOCKOUT_SUBJECT = 'Password reset required — {emp_id}'


def locked_message(employee):
    when = ''
    if employee.login_locked_until:
        when = ' You can try again after %s UTC.' % employee.login_locked_until.strftime('%H:%M')
    return (
        'Your account is temporarily blocked due to too many failed login attempts.'
        f'{when} Please wait, or contact HR / IT & Networks to reset your password.'
    )


def clear_login_lock(employee):
    if employee.failed_login_attempts or employee.login_locked_until:
        employee.failed_login_attempts = 0
        employee.login_locked_until = None
        employee.save(update_fields=['failed_login_attempts', 'login_locked_until'])


def register_failed_login(employee):
    """Record a failed login. Returns True if the account just got locked."""
    if employee.is_login_locked:
        return False
    employee.failed_login_attempts = (employee.failed_login_attempts or 0) + 1
    if employee.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
        employee.login_locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
        employee.failed_login_attempts = 0
        employee.save(update_fields=['failed_login_attempts', 'login_locked_until'])
        open_password_reset_ticket(employee)
        return True
    employee.save(update_fields=['failed_login_attempts'])
    return False


def attempts_left(employee):
    if employee.is_login_locked:
        return 0
    return max(0, MAX_LOGIN_ATTEMPTS - (employee.failed_login_attempts or 0))


def open_password_reset_ticket(employee):
    try:
        from hr_modules.models import NetworkTicket
        from hr_modules.views import notify_team
    except Exception:
        return None
    subject = LOCKOUT_SUBJECT.format(emp_id=employee.employee_id)
    if NetworkTicket.objects.filter(
            employee=employee, category='email', subject=subject,
            status__in=['pending', 'approved', 'in_progress']).exists():
        return None
    ticket = NetworkTicket.objects.create(
        employee=employee,
        category='email',
        assigned_team='networks',
        priority='high',
        status='approved',
        subject=subject,
        description=(
            f'{employee.full_name} ({employee.employee_id}) entered an incorrect password '
            f'{MAX_LOGIN_ATTEMPTS} times and the account is temporarily locked. '
            f'Please verify the identity and reset the password from the IT Help Desk.'
        ),
    )
    notify_team(
        'networks',
        'Password reset needed',
        f'Ticket #{ticket.pk}: {employee.full_name} ({employee.employee_id}) is locked after '
        f'{MAX_LOGIN_ATTEMPTS} failed login attempts. Please reset the password.',
        'warning',
        'networks_ticket_list',
    )
    return ticket
