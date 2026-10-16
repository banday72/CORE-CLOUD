"""Per-employee collaboration feature access (managed by Networks/IT).

Default is allow-everything: an employee is blocked for a feature only when
a :class:`collab.models.CollabAccess` row exists with the matching
``block_<feature>`` flag set. No row means full access.
"""

from employees.models import Employee

from .models import (
    FEATURE_CHAT, FEATURE_MAIL, FEATURE_MEETINGS, CollabAccess, block_field,
)

FEATURES = (FEATURE_MAIL, FEATURE_CHAT, FEATURE_MEETINGS)


def _validate(feature):
    if feature not in FEATURES:
        raise ValueError(f'Unknown feature: {feature}')


def blocked_features(employee):
    """Return the set of feature keys the employee is blocked from."""
    if employee is None or not employee.pk:
        return set()
    row = (CollabAccess.objects
           .filter(employee=employee)
           .only('block_mail', 'block_chat', 'block_meetings')
           .first())
    if row is None:
        return set()
    return {f for f in FEATURES if getattr(row, block_field(f))}


def is_blocked(employee, feature):
    """True when *employee* is blocked from *feature*."""
    _validate(feature)
    if employee is None or not employee.pk:
        return False
    return CollabAccess.objects.filter(employee=employee, **{block_field(feature): True}).exists()


def blocked_employee_ids(feature):
    """Pks of active employees blocked from *feature* (for excluding from pickers)."""
    _validate(feature)
    return set(
        CollabAccess.objects.filter(**{block_field(feature): True})
        .values_list('employee_id', flat=True)
    )


def accessible_employees(feature=None, exclude=None, **filters):
    """Active employees visible for a feature's picker/invite list."""
    qs = Employee.objects.filter(status='active').select_related('department')
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    if feature is not None:
        ids = blocked_employee_ids(feature)
        if ids:
            qs = qs.exclude(pk__in=ids)
    if filters:
        qs = qs.filter(**filters)
    return qs.order_by('first_name', 'last_name')


def can_manage_collab_access(user):
    """Networks team, IT managers and superusers may manage the rules."""
    if user is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    from employees.permissions import permissions_for_user
    return bool(permissions_for_user(user) & {'resolve_networks', 'manage_it_teams'})
