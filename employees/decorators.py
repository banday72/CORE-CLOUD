from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

from .permissions import permissions_for_user


def permission_required(*perms):
    required = set(perms)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            if permissions_for_user(user) & required:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'Access denied. Your designation does not allow this action.')
            return redirect('dashboard')
        return wrapper

    return decorator


def hr_required(view_func):
    return permission_required('dashboard_hr')(view_func)


def privilege_required(view_func):
    return permission_required('manage_access', 'view_audit', 'manage_slides', 'bulk_import')(view_func)


def collab_access_required(view_func):
    """Networks team (resolve_networks), IT managers (manage_it_teams), superusers."""
    return permission_required('resolve_networks', 'manage_it_teams')(view_func)