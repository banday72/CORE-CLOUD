from .models import Notification


def notify(employee, title, message, notif_type='info', link=''):
    """Create a notification for an employee (no-op if there is no employee)."""
    if not employee:
        return None
    return Notification.objects.create(
        employee=employee,
        title=title,
        message=message,
        notif_type=notif_type,
        link=link,
    )


def notify_user(user, title, message, notif_type='info', link=''):
    from employees.models import Employee
    employee = Employee.objects.filter(user=user).first()
    return notify(employee, title, message, notif_type, link)


def notify_reports_to(employee, title, message, notif_type='info', link=''):
    """Notify the employee's direct manager (reports_to)."""
    if employee and employee.reports_to:
        return notify(employee.reports_to, title, message, notif_type, link)
    return None