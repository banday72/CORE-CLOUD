from django.contrib.auth import logout
from django.shortcuts import redirect


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
