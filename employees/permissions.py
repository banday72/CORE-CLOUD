"""Designation-based permission model.

Every logged-in employee gets a set of permission tokens derived from their
designation, department and role.  These tokens drive the sidebar and the
server-side view decorators, so what you see is exactly what you can do.
Token names double as attribute names on the ``can`` object exposed to
templates (e.g. ``{% if can.manage_employees %}``).
"""

import re

HR_KEYWORDS = ('hr', 'humanresource', 'talent', 'recruit')
MANAGER_KEYWORDS = ('manager', 'director', 'supervisor', 'coordinator', 'head', 'lead', 'generalmanager')

ALL_PERMISSIONS = {
    'dashboard_hr',
    'view_employees',
    'manage_employees',
    'bulk_import',
    'manage_departments',
    'manage_access',
    'manage_employee_status',
    'view_audit',
    'manage_slides',
    'manage_faces',
    'manage_reviews',
    'manage_training',
    'ai_analytics',
    'manage_attendance',
    'manage_leaves',
    'manage_payroll',
    'manage_boutique',
    'view_reports',
    'manage_documents',
    'view_all_travel',
    'view_all_overtime',
    'approve_travel',
    'approve_overtime',
    'resolve_networks',
    'resolve_software',
    'resolve_hardware',
    'manage_it_teams',
    'manage_announcements',
    'manage_mail_settings',
    'view_soc',
    'respond_soc',
    'manage_soc',
}

IT_RESOLVE_PERMISSIONS = {'resolve_networks', 'resolve_software', 'resolve_hardware'}

SOC_PERMISSIONS = {'view_soc', 'respond_soc', 'manage_soc'}

HR_PERMISSIONS = set(ALL_PERMISSIONS) - IT_RESOLVE_PERMISSIONS - SOC_PERMISSIONS - {'manage_it_teams', 'manage_access'}

# C-level executives are company-wide administrators. Their designation is
# matched by is_chief_designation(), so they retain access across departments.
EXECUTIVE_PERMISSIONS = set(ALL_PERMISSIONS)

MANAGER_PERMISSIONS = {
    'dashboard_hr',
    'view_employees',
    'manage_faces',
    'manage_reviews',
    'manage_training',
    'ai_analytics',
    'manage_leaves',
    'view_reports',
    'manage_documents',
    'view_all_travel',
    'view_all_overtime',
    'approve_travel',
    'approve_overtime',
}

EMPLOYEE_PERMISSIONS = set()

PERMISSION_GROUPS = {
    'executive': EXECUTIVE_PERMISSIONS,
    'hr': HR_PERMISSIONS,
    'manager': MANAGER_PERMISSIONS,
    'employee': EMPLOYEE_PERMISSIONS,
}


def _words(text):
    return set(re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).split())


def permission_group(employee):
    if employee is None:
        return 'employee'
    from .models import is_chief_designation
    if is_chief_designation(employee.designation):
        return 'executive'
    if employee.role == 'hr' or employee.in_hr_department:
        return 'hr'
    if employee.role == 'manager':
        return 'manager'
    if getattr(employee, 'support_team', '') in ('networks', 'software', 'hardware'):
        return 'employee'
    words = _words(employee.designation)
    if words & set(HR_KEYWORDS):
        return 'hr'
    if words & set(MANAGER_KEYWORDS):
        return 'manager'
    return 'employee'


def permissions_for(employee):
    perms = set(PERMISSION_GROUPS[permission_group(employee)])
    team = getattr(employee, 'support_team', '')
    if team in ('networks', 'software', 'hardware'):
        perms.add('resolve_' + team)
        # IT support staff run the SOC: view alerts, respond (ack/escalate/lock).
        perms.update({'view_soc', 'respond_soc'})
    if team == 'networks':
        # Account authorization is an IT access-control responsibility.
        perms.add('manage_access')
    if getattr(employee, 'is_it_manager', False) or getattr(employee, 'it_role', ''):
        perms.add('manage_it_teams')
        perms.update({'view_soc', 'respond_soc', 'manage_soc'})
    return perms


def permissions_for_user(user):
    if user is None:
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSIONS)
    from .models import Employee
    try:
        employee = Employee.objects.select_related('department').get(user=user)
    except Employee.DoesNotExist:
        return set()
    return permissions_for(employee)


class Perms:
    def __init__(self, permissions):
        self._permissions = set(permissions)

    def __contains__(self, item):
        return item in self._permissions

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return name in self._permissions