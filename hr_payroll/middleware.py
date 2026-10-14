import time
import json
import logging
from django.core.cache import cache
from django.shortcuts import redirect
from django.contrib import messages


logger = logging.getLogger('hr_payroll')

USER_MAX_ATTEMPTS = 7
IP_MAX_ATTEMPTS = 20
WINDOW_SECONDS = 1800
LOCKOUT_SUBJECT = 'Password reset required — {emp_id}'


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_login_post = request.path == '/login/' and request.method == 'POST'
        ip = username = None
        if is_login_post:
            ip = self.get_client_ip(request)
            username = (request.POST.get('username') or '').strip()
            attempts = cache.get(f'login_attempts_{ip}', 0)
            user_attempts = cache.get(f'login_attempts_user_{username}', 0)
            if attempts >= IP_MAX_ATTEMPTS or user_attempts >= USER_MAX_ATTEMPTS:
                messages.error(request, 'Too many login attempts. Please wait and try again later.')
                return redirect('login')

        response = self.get_response(request)

        if is_login_post:
            if request.user.is_authenticated:
                cache.delete(f'login_attempts_{ip}')
                cache.delete(f'login_attempts_user_{username}')
                self._clear_failed_attempts(username)
            else:
                cache.set(f'login_attempts_{ip}', cache.get(f'login_attempts_{ip}', 0) + 1, WINDOW_SECONDS)
                cache.set(f'login_attempts_user_{username}', cache.get(f'login_attempts_user_{username}', 0) + 1, WINDOW_SECONDS)
                self._register_failed_attempt(username)

        return response

    def _clear_failed_attempts(self, username):
        if not username:
            return
        try:
            from employees.models import Employee
            Employee.objects.filter(employee_id=username, failed_login_attempts__gt=0).update(failed_login_attempts=0)
        except Exception:
            logger.warning('Failed to clear login attempts for %s', username, exc_info=True)

    def _register_failed_attempt(self, username):
        if not username:
            return
        try:
            from employees.models import Employee
            emp = Employee.objects.filter(employee_id=username).first()
            if emp is None or emp.user is None:
                return
            emp.failed_login_attempts = (emp.failed_login_attempts or 0) + 1
            if emp.failed_login_attempts >= USER_MAX_ATTEMPTS:
                self._create_reset_ticket(emp)
                emp.failed_login_attempts = 0
            emp.save(update_fields=['failed_login_attempts'])
        except Exception:
            logger.warning('Failed to register login attempt for %s', username, exc_info=True)

    def _create_reset_ticket(self, emp):
        try:
            from hr_modules.models import NetworkTicket
            from hr_modules.views import notify_team
        except Exception:
            logger.warning('Could not import ticket helpers', exc_info=True)
            return
        subject = LOCKOUT_SUBJECT.format(emp_id=emp.employee_id)
        already_open = NetworkTicket.objects.filter(
            employee=emp, category='email', subject=subject,
            status__in=['pending', 'approved', 'in_progress'],
        ).exists()
        if already_open:
            return
        ticket = NetworkTicket.objects.create(
            employee=emp,
            category='email',
            assigned_team='networks',
            priority='high',
            status='approved',
            subject=subject,
            description=(
                f'{emp.full_name} ({emp.employee_id}) entered an incorrect password '
                f'{USER_MAX_ATTEMPTS} times. Please verify the identity and reset the '
                f'password from the IT Help Desk (Networks team has the reset option).'
            ),
        )
        notify_team(
            'networks',
            'Password reset needed',
            f'Ticket #{ticket.pk}: {emp.full_name} ({emp.employee_id}) had '
            f'{USER_MAX_ATTEMPTS} failed login attempts. Please reset the password.',
            'warning',
            'networks_ticket_list',
        )

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')
