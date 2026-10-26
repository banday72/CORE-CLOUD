from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied


class AuthorizedUserBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return None

        if not user.check_password(password):
            return None

        from soc.models import user_is_blacklisted
        if user_is_blacklisted(username):
            raise PermissionDenied('Account has been disabled by SOC')

        if user.is_superuser:
            return user

        from employees.models import Employee
        try:
            employee = user.employee
        except Employee.DoesNotExist:
            return None
        if employee.is_login_locked:
            raise PermissionDenied('Account locked after too many failed login attempts')
        if employee.status == 'active' and employee.is_authorized:
            return user
        return None
