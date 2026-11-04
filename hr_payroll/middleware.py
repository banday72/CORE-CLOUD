from django.contrib.auth import logout
from django.shortcuts import redirect
from django.conf import settings
from django.utils import timezone


class ActiveEmployeeMiddleware:
    """Revoke live sessions when an employee is inactive or terminated."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not user.is_superuser:
            employee = getattr(user, 'employee', None)
            if employee is None or employee.status != 'active':
                logout(request)
                return redirect('login')
        return self.get_response(request)


class IdleSessionTimeoutMiddleware:
    """Log authenticated users out after a period without a request."""

    SESSION_KEY = '_cc_last_activity'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            now = timezone.now().timestamp()
            last_activity = request.session.get(self.SESSION_KEY)
            timeout = getattr(settings, 'SESSION_IDLE_TIMEOUT', 120)

            if last_activity is not None and now - float(last_activity) >= timeout:
                logout(request)
                return redirect('login')

            request.session[self.SESSION_KEY] = now

        response = self.get_response(request)
        if user is not None and user.is_authenticated:
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
        return response
