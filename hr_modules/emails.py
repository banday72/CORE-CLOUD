"""Email helpers for the IT / Networks help desk.

Sending never raises: if email is not configured (console backend) or a
recipient has no address, it silently does nothing. Configure real delivery by
setting EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD environment vars.
"""

from django.conf import settings
from django.core.mail import send_mail


def send_ticket_email(employee, subject, body):
    """Send a plain-text email to an employee, if they have an address."""
    if not employee or not getattr(employee, 'email', ''):
        return False
    try:
        send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@corecloud.local'),
            [employee.email],
            fail_silently=True,
        )
        return True
    except Exception:
        return False


def email_team_members(team, subject, body, exclude_pk=None):
    """Email every active member of a support team, optionally excluding one."""
    from employees.models import Employee
    members = Employee.objects.filter(status='active', support_team=team).exclude(pk=exclude_pk or 0)
    sent = 0
    for emp in members:
        if send_ticket_email(emp, subject, body):
            sent += 1
    return sent
