import csv
import io
import base64
import json
from datetime import date, timedelta
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.uploadedfile import UploadedFile
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Count, Q
from django.core.paginator import Paginator
from .models import Department, Employee, AuditLog, LoginSlide, managers_queryset, chief_id_prefix, MANAGEMENT_DEPARTMENT_NAMES, default_password_for
from .forms import DepartmentForm, EmployeeForm, ProfileForm, LoginSlideForm
from .decorators import permission_required, hr_required, privilege_required
from .permissions import permissions_for_user
from .audit import log_audit
from .ajax import is_ajax, json_ok, json_err


def generate_employee_id(designation=None, department=None):
    prefix = chief_id_prefix(designation)
    department_name = (getattr(department, 'name', department) or '').strip().lower()
    if prefix is None and department_name in MANAGEMENT_DEPARTMENT_NAMES:
        prefix = 'C'
    if prefix is None:
        prefix = 'EMP'
    highest = 0
    for value in Employee.objects.filter(
            employee_id__startswith=prefix).values_list('employee_id', flat=True):
        suffix = value[len(prefix):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return '%s%03d' % (prefix, highest + 1)


def get_employee(user):
    try:
        return Employee.objects.get(user=user)
    except Employee.DoesNotExist:
        return None


PROFILE_MIME = {
    'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'gif': 'image/gif', 'webp': 'image/webp', 'svg': 'image/svg+xml',
    'pdf': 'application/pdf',
}


def _compress_image(payload, ext):
    """Shrink large photos before base64-encoding them into the database.

    Returns (payload, ext) on success, or None when the input is not an
    image we can safely re-encode (e.g. SVG, PDF, animated GIF, corrupt file).
    """
    if ext not in ('png', 'jpg', 'jpeg', 'webp', 'bmp'):
        return None
    try:
        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(payload))
        img.load()
        if img.width > 1600:
            ratio = 1600 / float(img.width)
            img = img.resize((1600, max(1, int(img.height * ratio))), Image.LANCZOS)
        out = BytesIO()
        if img.mode in ('RGBA', 'LA', 'P'):
            img.save(out, format='PNG', optimize=True)
            return out.getvalue(), 'png'
        img.convert('RGB').save(out, format='JPEG', quality=82, optimize=True)
        return out.getvalue(), 'jpg'
    except Exception:
        return None


def store_picture_as_b64(form, instance):
    upload = form.cleaned_data.get('profile_picture')
    if not isinstance(upload, UploadedFile):
        return
    name = getattr(upload, 'name', '') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    mime = PROFILE_MIME.get(ext, 'application/octet-stream')
    try:
        upload.seek(0)
        payload = upload.read()
    except (ValueError, OSError):
        return
    compressed = _compress_image(payload, ext)
    if compressed:
        payload, ext = compressed
        mime = PROFILE_MIME.get(ext, mime)
    instance.profile_picture_b64 = 'data:%s;base64,%s' % (
        mime, base64.b64encode(payload).decode('utf-8'))
    instance.profile_picture = None


def file_to_data_uri(upload):
    name = getattr(upload, 'name', '') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    mime = PROFILE_MIME.get(ext, 'application/octet-stream')
    try:
        upload.seek(0)
        payload = upload.read()
    except (ValueError, OSError):
        return None
    compressed = _compress_image(payload, ext)
    if compressed:
        payload, ext = compressed
        mime = PROFILE_MIME.get(ext, mime)
    return 'data:%s;base64,%s' % (mime, base64.b64encode(payload).decode('utf-8'))


@login_required
def dashboard(request):
    employee = get_employee(request.user)
    from leaves.models import Leave
    from payroll.models import Payroll
    from attendance.models import Attendance
    from datetime import date

    if employee and employee.must_change_password:
        messages.warning(request, 'You must change your password before continuing.')
        return redirect('change_password')

    perms = permissions_for_user(request.user)
    show_hr_dashboard = bool(perms & {'dashboard_hr', 'view_employees', 'manage_employees'})

    if employee and not show_hr_dashboard:
        today = date.today()
        my_attendance = Attendance.objects.filter(employee=employee, date=today).first()
        my_leaves = Leave.objects.filter(employee=employee).count()
        my_pending_leaves = Leave.objects.filter(employee=employee, status='pending').count()
        my_payrolls = Payroll.objects.filter(employee=employee)[:5]

        status_colors = {
            'present': '#1cc88a', 'absent': '#e74a3b', 'half_day': '#36b9cc',
            'late': '#f6c23e', 'holiday': '#9b59b6',
        }
        label_map = dict(Attendance.STATUS_CHOICES)
        att_labels, att_counts, att_colors = [], [], []
        att_rows = (Attendance.objects.filter(employee=employee, date__gt=today - timedelta(days=30))
                    .values('status').annotate(total=Count('id')).order_by('status'))
        for row in att_rows:
            att_labels.append(label_map.get(row['status'], row['status']))
            att_counts.append(row['total'])
            att_colors.append(status_colors.get(row['status'], '#2980b9'))

        att_chart = ''
        if att_labels:
            att_chart = json.dumps({
                'type': 'doughnut',
                'data': {'labels': att_labels, 'datasets': [{
                    'data': att_counts, 'backgroundColor': att_colors, 'borderWidth': 0}]},
                'options': {'responsive': True, 'cutout': '62%',
                            'plugins': {'legend': {'position': 'bottom', 'labels': {
                                'font': {'size': 10}, 'boxWidth': 10, 'usePointStyle': True}}}},
            })

        salary_months, salary_values = [], []
        for p in my_payrolls:
            salary_months.append(f'{p.get_month_display()} {p.year}')
            salary_values.append(float(p.net_salary))
        salary_months.reverse()
        salary_values.reverse()

        salary_chart = ''
        if salary_months:
            salary_chart = json.dumps({
                'type': 'line',
                'data': {'labels': salary_months, 'datasets': [{
                    'label': 'Net Salary', 'data': salary_values,
                    'borderColor': '#2980b9', 'backgroundColor': 'rgba(41,128,185,.15)',
                    'fill': True, 'tension': .3, 'pointRadius': 3}]},
                'options': {'responsive': True,
                            'plugins': {'legend': {'display': False}},
                            'scales': {'y': {'beginAtZero': True, 'ticks': {'font': {'size': 10}}},
                                       'x': {'ticks': {'font': {'size': 10}}}}},
            })

        context = {
            'employee': employee,
            'my_attendance': my_attendance,
            'my_leaves_count': my_leaves,
            'my_pending_leaves': my_pending_leaves,
            'my_payrolls': my_payrolls,
            'att_chart': att_chart,
            'salary_chart': salary_chart,
            'is_employee': True,
            'is_hr': False,
            'permissions': perms,
        }
    else:
        total_employees = Employee.objects.filter(status='active').count()
        total_departments = Department.objects.count()
        recent_employees = Employee.objects.select_related('department', 'reports_to').all()[:5]
        pending_leaves = Leave.objects.filter(status='pending').count()
        draft_payrolls = Payroll.objects.filter(status='draft').count()
        today_birthdays = Employee.objects.filter(
            date_of_birth__month=date.today().month,
            date_of_birth__day=date.today().day,
            status='active'
        )
        context = {
            'total_employees': total_employees,
            'total_departments': total_departments,
            'recent_employees': recent_employees,
            'pending_leaves': pending_leaves,
            'draft_payrolls': draft_payrolls,
            'is_employee': False,
            'is_hr': bool(show_hr_dashboard),
            'today_birthdays': today_birthdays,
            'permissions': perms,
        }
    from hr_modules.models import Announcement
    from django.db.models import Q
    today = date.today()
    context['announcements'] = Announcement.objects.filter(
        Q(publish_from__isnull=True) | Q(publish_from__lte=today),
        Q(publish_until__isnull=True) | Q(publish_until__gte=today),
    )[:5]
    context['today_birthdays'] = Employee.objects.filter(
        date_of_birth__month=today.month, date_of_birth__day=today.day, status='active')
    context['work_anniversaries'] = Employee.objects.filter(
        date_of_joining__month=today.month, date_of_joining__day=today.day, status='active')
    return render(request, 'dashboard.html', context)


@login_required
@permission_required('view_employees')
def employee_list(request):
    employees = Employee.objects.select_related('department', 'reports_to').all()
    search = request.GET.get('search', '')
    department_id = request.GET.get('department', '')
    status = request.GET.get('status', '')
    if search:
        employees = employees.filter(
            Q(employee_id__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(designation__icontains=search) |
            Q(department__name__icontains=search) |
            Q(city__icontains=search) |
            Q(reports_to__first_name__icontains=search) |
            Q(reports_to__last_name__icontains=search) |
            Q(reports_to__employee_id__icontains=search)
        )
    if department_id:
        employees = employees.filter(department_id=department_id)
    if status:
        employees = employees.filter(status=status)
    paginator = Paginator(employees, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    departments = Department.objects.all()
    return render(request, 'employees/employee_list.html', {
        'employees': page_obj,
        'page_obj': page_obj,
        'search': search,
        'departments': departments,
        'selected_department': department_id,
        'selected_status': status,
    })


@login_required
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    current_employee = get_employee(request.user)
    perms = permissions_for_user(request.user)
    is_self = current_employee is not None and current_employee.pk == employee.pk
    if not is_self and not (perms & {'view_employees', 'manage_employees'}):
        messages.error(request, 'Access denied. You can only view your own profile.')
        return redirect('dashboard')
    return render(request, 'employees/employee_detail.html', {
        'employee': employee,
        'is_hr': bool(perms & {'view_employees', 'manage_employees'}),
        'can_manage_employees': bool(perms & {'manage_employees'}),
    })


def _creates_report_cycle(employee, new_manager):
    seen = set()
    node = new_manager
    while node is not None and node.pk not in seen:
        if node.pk == employee.pk:
            return True
        seen.add(node.pk)
        node = node.reports_to
    return False


@login_required
def my_manager(request):
    employee = get_employee(request.user)
    if not employee:
        messages.error(request, 'No employee profile is linked to your account.')
        return redirect('dashboard')

    managers = managers_queryset().exclude(pk=employee.pk)

    if request.method == 'POST':
        selected = request.POST.get('reports_to', '').strip()
        if selected in ('', 'none'):
            previous = employee.reports_to.full_name if employee.reports_to else 'none'
            employee.reports_to = None
            employee.save(update_fields=['reports_to'])
            log_audit(user=request.user, action='update', model_name='Employee',
                      object_id=employee.employee_id,
                      description=f'Removed own manager (was {previous})', request=request)
            messages.success(request, 'Your manager has been removed.')
            return redirect('my_manager')

        try:
            new_manager = Employee.objects.select_related('department').get(
                pk=selected, status='active')
        except (Employee.DoesNotExist, ValueError):
            messages.error(request, 'That manager does not exist or is no longer active.')
            return redirect('my_manager')

        if new_manager.pk == employee.pk:
            messages.error(request, 'You cannot be your own manager.')
            return redirect('my_manager')
        if not (new_manager.role in ('manager', 'hr') or new_manager.is_chief):
            messages.error(request, 'You can only report to a Manager, HR or a Chief.')
            return redirect('my_manager')
        if _creates_report_cycle(employee, new_manager):
            messages.error(request, 'That choice would create a circular reporting line.')
            return redirect('my_manager')

        employee.reports_to = new_manager
        employee.save(update_fields=['reports_to'])
        log_audit(user=request.user, action='update', model_name='Employee',
                  object_id=employee.employee_id,
                  description=f'Set own manager to {new_manager.full_name}', request=request)
        messages.success(request, f'Manager updated to {new_manager.full_name}.')
        return redirect('my_manager')

    return render(request, 'employees/my_manager.html', {
        'employee': employee,
        'managers': managers,
        'subordinates': employee.subordinates.filter(status='active').select_related('department'),
    })


@login_required
@permission_required('manage_employees')
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            emp = form.save(commit=False)
            store_picture_as_b64(form, emp)
            emp.employee_id = generate_employee_id(emp.designation, emp.department)
            emp.save()
            user = User.objects.create_user(
                username=emp.employee_id,
                email=emp.email,
                password=default_password_for(emp.employee_id),
                first_name=emp.first_name,
                last_name=emp.last_name,
            )
            emp.user = user
            emp.must_change_password = True
            emp.save()
            log_audit(user=request.user, action='create', model_name='Employee',
                      object_id=emp.employee_id, description=f'Created employee {emp.full_name}', request=request)
            messages.success(request, f'Employee created. Login: {emp.employee_id} / {default_password_for(emp.employee_id)}. They must change their password on first login.')
            return redirect('employee_list')
    else:
        form = EmployeeForm(user=request.user)
        form.fields['employee_id_preview'].initial = generate_employee_id()
    return render(request, 'employees/employee_form.html',
                  {'form': form, 'title': 'Add Employee', 'auto_employee_id': True})


@login_required
def next_employee_id(request):
    designation = request.GET.get('designation', '').strip()
    department = None
    department_id = request.GET.get('department_id', '')
    if department_id.isdigit():
        department = Department.objects.filter(pk=int(department_id)).first()
    return JsonResponse({'employee_id': generate_employee_id(designation, department)})


@login_required
@permission_required('manage_employees')
def employee_update(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        previous_status = employee.status
        form = EmployeeForm(request.POST, request.FILES, instance=employee, user=request.user)
        if form.is_valid():
            emp = form.save(commit=False)
            store_picture_as_b64(form, emp)
            emp.save()
            if previous_status == 'active' and emp.status != 'active':
                emp.is_authorized = False
                emp.approved_by_manager = False
                emp.approved_by = None
                emp.approved_at = None
                emp.login_locked_until = None
                emp.failed_login_attempts = 0
                emp.save(update_fields=[
                    'is_authorized', 'approved_by_manager', 'approved_by',
                    'approved_at', 'login_locked_until', 'failed_login_attempts',
                ])
                log_audit(
                    user=request.user,
                    action='deauthorize',
                    model_name='Employee',
                    object_id=emp.employee_id,
                    description=f'Account access revoked because {emp.full_name} is {emp.status}.',
                    request=request,
                )
            log_audit(user=request.user, action='update', model_name='Employee',
                      object_id=employee.employee_id, description=f'Updated employee {employee.full_name}', request=request)
            messages.success(request, 'Employee updated successfully.')
            return redirect('employee_detail', pk=pk)
    else:
        form = EmployeeForm(instance=employee, user=request.user)
    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Edit Employee'})


@login_required
@permission_required('manage_employees')
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        name = employee.full_name
        emp_id = employee.employee_id
        if employee.user:
            employee.user.delete()
        employee.delete()
        log_audit(user=request.user, action='delete', model_name='Employee',
                  object_id=emp_id, description=f'Deleted employee {name}', request=request)
        if is_ajax(request):
            return json_ok('Employee deleted successfully.')
        messages.success(request, 'Employee deleted successfully.')
        return redirect('employee_list')
    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})


@login_required
@permission_required('manage_departments')
def department_list(request):
    departments = Department.objects.all()
    return render(request, 'employees/department_list.html', {'departments': departments})


@login_required
@permission_required('manage_departments')
def department_create(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            dept = form.save()
            log_audit(user=request.user, action='create', model_name='Department',
                      object_id=dept.name, description=f'Created department {dept.name}', request=request)
            messages.success(request, 'Department created successfully.')
            return redirect('department_list')
    else:
        form = DepartmentForm()
    return render(request, 'employees/department_form.html', {'form': form, 'title': 'Add Department'})


@login_required
@permission_required('manage_departments')
def department_update(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            log_audit(user=request.user, action='update', model_name='Department',
                      object_id=department.name, description=f'Updated department {department.name}', request=request)
            messages.success(request, 'Department updated successfully.')
            return redirect('department_list')
    else:
        form = DepartmentForm(instance=department)
    return render(request, 'employees/department_form.html', {'form': form, 'title': 'Edit Department'})


@login_required
@permission_required('manage_departments')
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        name = department.name
        department.delete()
        log_audit(user=request.user, action='delete', model_name='Department',
                  object_id=name, description=f'Deleted department {name}', request=request)
        messages.success(request, 'Department deleted successfully.')
        return redirect('department_list')
    return render(request, 'employees/department_confirm_delete.html', {'department': department})


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            employee = get_employee(request.user)
            if employee and employee.must_change_password:
                employee.must_change_password = False
                employee.save()
            log_audit(user=request.user, action='password_change', model_name='User',
                      object_id=request.user.username, description='Password changed', request=request)
            messages.success(request, 'Your password has been changed successfully.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'registration/change_password.html', {'form': form})


@login_required
@permission_required('manage_access')
def authorized_users(request):
    employees = Employee.objects.select_related('user', 'department').all()
    search = request.GET.get('search', '')
    auth_filter = request.GET.get('auth_filter', '')
    department_id = request.GET.get('department', '')
    if search:
        employees = employees.filter(
            Q(employee_id__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(designation__icontains=search) |
            Q(department__name__icontains=search)
        )
    if department_id:
        employees = employees.filter(department_id=department_id)
    if auth_filter == 'authorized':
        employees = employees.filter(is_authorized=True)
    elif auth_filter == 'unauthorized':
        employees = employees.filter(is_authorized=False)
    paginator = Paginator(employees, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'employees/authorized_users.html', {
        'employees': page_obj,
        'page_obj': page_obj,
        'search': search,
        'auth_filter': auth_filter,
        'departments': Department.objects.all(),
        'selected_department': department_id,
    })


@login_required
@permission_required('manage_access')
def toggle_authorize(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        employee.is_authorized = not employee.is_authorized
        if not employee.is_authorized:
            employee.approved_by_manager = False
            employee.approved_by = None
            employee.approved_at = None
        employee.save()
        ajax_message = None
        ajax_type = 'info'
        if employee.is_authorized:
            action = 'authorize'
            if employee.role in ('hr', 'manager'):
                employee.approved_by_manager = True
                employee.approved_by = request.user
                from django.utils import timezone
                employee.approved_at = timezone.now()
                employee.save()
                if new_password and employee.user:
                    employee.user.set_password(new_password)
                    employee.user.save()
                    ajax_message = f'{employee.full_name} (HR/Manager) authorized directly. Username: {employee.employee_id} | Password: {new_password}'
                else:
                    ajax_message = f'{employee.full_name} (HR/Manager) authorized directly. Username: {employee.employee_id} | Default password: {default_password_for(employee.employee_id)}'
                messages.success(request, ajax_message)
            else:
                ajax_message = f'{employee.full_name} authorized by you. Waiting for Manager approval before they can login.'
                ajax_type = 'info'
                messages.info(request, ajax_message)
        else:
            action = 'deauthorize'
            ajax_message = f'{employee.full_name} has been deauthorized. They can no longer login.'
            ajax_type = 'warning'
            messages.warning(request, ajax_message)
        log_audit(user=request.user, action=action, model_name='Employee',
                  object_id=employee.employee_id, description=f'{action.title()}d {employee.full_name}', request=request)
        if is_ajax(request):
            state = 'approved' if (employee.is_authorized and employee.approved_by_manager) else (
                'active_role' if (employee.is_authorized and employee.role in ('hr', 'manager')) else (
                    'pending' if employee.is_authorized else 'unauthorized'))
            return json_ok(ajax_message, type=ajax_type, is_authorized=employee.is_authorized,
                           approved_by_manager=employee.approved_by_manager, state=state)
    return redirect('authorized_users')


@login_required
@permission_required('approve_access')
def pending_approvals(request):
    employee = get_employee(request.user)
    is_manager = request.user.is_superuser or permissions_for_user(request.user) & {'approve_access'}
    if not is_manager:
        messages.error(request, 'Only Managers can access this page.')
        return redirect('dashboard')

    pending = Employee.objects.select_related('department', 'approved_by').filter(
        is_authorized=True, approved_by_manager=False, status='active', role='employee'
    )
    search = request.GET.get('search', '')
    if search:
        pending = pending.filter(
            Q(employee_id__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    paginator = Paginator(pending, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'employees/pending_approvals.html', {
        'pending_employees': page_obj,
        'page_obj': page_obj,
        'search': search,
    })


@login_required
@permission_required('approve_access')
def manager_approve(request, pk):
    employee_obj = get_employee(request.user)
    is_manager = request.user.is_superuser or permissions_for_user(request.user) & {'approve_access'}
    if not is_manager:
        messages.error(request, 'Only Managers can approve authorizations.')
        return redirect('dashboard')

    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        ajax_message = None
        ajax_type = 'success'
        if action == 'approve':
            emp.approved_by_manager = True
            emp.approved_by = request.user
            from django.utils import timezone
            emp.approved_at = timezone.now()
            emp.save()
            new_password = request.POST.get('new_password', '').strip()
            if new_password and emp.user:
                emp.user.set_password(new_password)
                emp.user.save()
                ajax_message = f'{emp.full_name} approved. They can now login. Username: {emp.employee_id} | Password: {new_password}'
            else:
                ajax_message = f'{emp.full_name} approved. They can now login. Username: {emp.employee_id} | Default password: {default_password_for(emp.employee_id)}'
            messages.success(request, ajax_message)
            log_audit(user=request.user, action='authorize', model_name='Employee',
                      object_id=emp.employee_id, description=f'Manager approved {emp.full_name}', request=request)
        elif action == 'reject':
            emp.is_authorized = False
            emp.approved_by_manager = False
            emp.save()
            ajax_message = f'{emp.full_name} authorization rejected.'
            ajax_type = 'warning'
            messages.warning(request, ajax_message)
            log_audit(user=request.user, action='deauthorize', model_name='Employee',
                      object_id=emp.employee_id, description=f'Manager rejected {emp.full_name}', request=request)
        if is_ajax(request):
            if not ajax_message:
                return json_err('Unknown action.')
            return json_ok(ajax_message, type=ajax_type, action=action)
    return redirect('pending_approvals')


@login_required
@permission_required('manage_slides')
def login_slide_list(request):
    slides = LoginSlide.objects.all()
    if request.method == 'POST':
        form = LoginSlideForm(request.POST, request.FILES)
        if form.is_valid() and request.FILES.get('picture'):
            data_uri = file_to_data_uri(form.cleaned_data['picture'])
            if data_uri:
                slide = LoginSlide.objects.create(
                    name=form.cleaned_data.get('name', '').strip(),
                    picture_b64=data_uri,
                    picture_name=getattr(form.cleaned_data['picture'], 'name', '') or '',
                    is_active=form.cleaned_data.get('is_active', True),
                    sort_order=form.cleaned_data.get('sort_order') or 0,
                )
                log_audit(user=request.user, action='create', model_name='LoginSlide',
                          object_id=slide.pk, description=f'Added login background {slide}', request=request)
                messages.success(request, 'Login background added.')
            else:
                messages.error(request, 'Could not read the image file.')
        else:
            messages.error(request, 'Please choose a valid image file.')
        return redirect('login_slide_list')
    form = LoginSlideForm()
    return render(request, 'employees/login_slide_list.html', {'slides': slides, 'form': form})


@login_required
@permission_required('manage_slides')
def login_slide_delete(request, pk):
    slide = get_object_or_404(LoginSlide, pk=pk)
    if request.method == 'POST':
        name = str(slide)
        slide.delete()
        log_audit(user=request.user, action='delete', model_name='LoginSlide',
                  object_id=pk, description=f'Deleted login background {name}', request=request)
        if is_ajax(request):
            return json_ok('Login background deleted.')
        messages.success(request, 'Login background deleted.')
    return redirect('login_slide_list')


@login_required
@permission_required('manage_slides')
def login_slide_toggle(request, pk):
    slide = get_object_or_404(LoginSlide, pk=pk)
    if request.method == 'POST':
        slide.is_active = not slide.is_active
        slide.save(update_fields=['is_active'])
        state = 'enabled' if slide.is_active else 'disabled'
        log_audit(user=request.user, action='update', model_name='LoginSlide',
                  object_id=pk, description=f'{state.title()} login background {slide}', request=request)
        if is_ajax(request):
            return json_ok(f'Login background {state}.', type='info', is_active=slide.is_active)
        messages.info(request, f'Login background {state}.')
    return redirect('login_slide_list')


@login_required
@permission_required('bulk_import')
def bulk_import_employees(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        try:
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            created_count = 0
            skipped_count = 0
            errors = []

            for row in reader:
                try:
                    emp_id = row.get('employee_id', '').strip()
                    first_name = row.get('first_name', '').strip()
                    last_name = row.get('last_name', '').strip()
                    email = row.get('email', '').strip()
                    department_name = row.get('department', '').strip()
                    designation = row.get('designation', '').strip()
                    salary = row.get('salary', '0').strip()
                    role = row.get('role', 'employee').strip().lower()

                    if not first_name or not last_name or not email:
                        skipped_count += 1
                        continue

                    department = None
                    if department_name:
                        department, _ = Department.objects.get_or_create(name=department_name)

                    if not emp_id:
                        emp_id = generate_employee_id(designation, department)
                    elif Employee.objects.filter(employee_id=emp_id).exists():
                        skipped_count += 1
                        continue

                    if Employee.objects.filter(email=email).exists():
                        skipped_count += 1
                        continue

                    emp = Employee.objects.create(
                        employee_id=emp_id,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        department=department,
                        designation=designation,
                        salary=float(salary),
                        role=role if role in ('employee', 'hr', 'manager') else 'employee',
                        date_of_joining=date.today(),
                        status='active',
                    )

                    user = User.objects.create_user(
                        username=emp_id,
                        email=email,
                        password=default_password_for(emp_id),
                        first_name=first_name,
                        last_name=last_name,
                    )
                    emp.user = user
                    emp.must_change_password = True
                    emp.save()
                    created_count += 1

                except Exception as e:
                    skipped_count += 1
                    errors.append(f"Row error: {str(e)}")

            log_audit(user=request.user, action='create', model_name='Employee',
                      description=f'Bulk import: {created_count} created, {skipped_count} skipped', request=request)

            if created_count > 0:
                messages.success(request, f'Successfully imported {created_count} employees. {skipped_count} skipped.')
            else:
                messages.warning(request, f'No employees imported. {skipped_count} rows skipped.')

            if errors:
                for err in errors[:5]:
                    messages.warning(request, err)

            return redirect('employee_list')

        except Exception as e:
            messages.error(request, f'Error reading CSV file: {str(e)}')
            return redirect('employee_list')

    return render(request, 'employees/bulk_import.html')


@login_required
@permission_required('view_audit')
def audit_log_list(request):
    logs = AuditLog.objects.select_related('user').all()
    search = request.GET.get('search', '')
    action_filter = request.GET.get('action', '')
    if search:
        logs = logs.filter(
            Q(description__icontains=search) |
            Q(object_id__icontains=search) |
            Q(user__username__icontains=search)
        )
    if action_filter:
        logs = logs.filter(action=action_filter)
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'employees/audit_log.html', {
        'logs': page_obj,
        'page_obj': page_obj,
        'search': search,
        'action_filter': action_filter,
    })


@login_required
def profile_update(request):
    if not request.user.is_superuser:
        messages.error(request, 'Only administrators can access profile settings.')
        return redirect('dashboard')
    user = request.user
    employee = get_employee(user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            if employee:
                try:
                    if 'profile_picture' in request.FILES:
                        f = request.FILES['profile_picture']
                        ext = f.name.rsplit('.', 1)[-1].lower()
                        mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'pdf': 'application/pdf'}
                        mime = mime_map.get(ext, 'application/octet-stream')
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                        employee.profile_picture_b64 = f'data:{mime};base64,{b64}'
                    if request.POST.get('designation'):
                        employee.designation = request.POST['designation']
                    employee.save()
                except Exception as e:
                    messages.warning(request, f'Profile saved but file upload failed: {str(e)}')
                    return redirect('profile_update')
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile_update')
    else:
        form = ProfileForm(instance=user)
    return render(request, 'employees/profile_update.html', {
        'form': form,
        'employee': employee,
    })


@login_required
def dashboard_stats(request):
    from django.db.models import Count, Avg
    from attendance.models import Attendance
    from datetime import date, timedelta

    depts = Department.objects.annotate(count=Count('employee')).filter(count__gt=0)
    dept_labels = [d.name for d in depts]
    dept_counts = [d.count for d in depts]

    today = date.today()
    statuses = Attendance.objects.filter(date=today).values('status').annotate(count=Count('id'))
    att_map = {s['status']: s['count'] for s in statuses}
    att_labels = ['Present', 'Absent', 'Late', 'Half Day', 'Holiday']
    att_counts = [att_map.get('present', 0), att_map.get('absent', 0), att_map.get('late', 0),
                  att_map.get('half_day', 0), att_map.get('holiday', 0)]

    dept_salaries = Department.objects.annotate(avg_sal=Avg('employee__salary')).filter(avg_sal__isnull=False)
    sal_labels = [d.name for d in dept_salaries]
    sal_totals = [float(d.avg_sal) for d in dept_salaries]

    return JsonResponse({
        'dept_labels': dept_labels, 'dept_counts': dept_counts,
        'attendance_labels': att_labels, 'attendance_counts': att_counts,
        'salary_labels': sal_labels, 'salary_totals': sal_totals,
    })


class LockoutLoginView(LoginView):
    template_name = 'registration/login.html'

    def form_valid(self, form):
        from .models import find_employee_by_id
        from .lockout import clear_login_lock
        from .audit import log_audit
        username = self.request.POST.get('username', '')
        employee = find_employee_by_id(username)
        unlocked = False
        if employee and not employee.is_login_locked:
            unlocked = bool(employee.failed_login_attempts or employee.login_locked_until)
            clear_login_lock(employee)
        result = super().form_valid(form)
        log_audit(
            user=form.get_user(),
            action='login', model_name='User',
            object_id=form.get_user().username,
            description=f'User logged in ({username})',
            request=self.request, category='auth', outcome='success',
        )
        if unlocked and employee:
            log_audit(
                user=form.get_user(), action='unlock', model_name='Employee',
                object_id=employee.employee_id,
                description=f'Login lock cleared for {employee.full_name}',
                request=self.request, category='auth', outcome='success',
            )
        return result

    def form_invalid(self, form):
        from .models import find_employee_by_id
        from .lockout import register_failed_login, locked_message
        from .audit import log_audit
        username = (self.request.POST.get('username') or '').strip()
        employee = find_employee_by_id(username)
        from soc.models import user_is_blacklisted
        if user_is_blacklisted(username):
            log_audit(
                user=employee.user if employee else None, action='login_failed',
                model_name='Employee',
                object_id=employee.employee_id if employee else username[:100],
                description=f'Login attempt on SOC-blacklisted account ({username})',
                request=self.request, category='auth', outcome='failure',
                severity='high',
            )
            messages.error(
                self.request,
                'Your account has been disabled by IT & Networks. '
                'Please contact the IT Help Desk.')
            return super().form_invalid(form)
        if employee is not None:
            if employee.is_login_locked:
                log_audit(
                    user=employee.user, action='login_failed',
                    model_name='Employee', object_id=employee.employee_id,
                    description=f'Login attempt while account is locked ({username})',
                    request=self.request, category='auth', outcome='failure',
                    severity='medium',
                )
                messages.error(self.request, locked_message(employee))
            elif register_failed_login(employee):
                from .lockout import MAX_LOGIN_ATTEMPTS
                log_audit(
                    user=employee.user, action='lockout',
                    model_name='Employee', object_id=employee.employee_id,
                    description=(
                        f'Account locked after {MAX_LOGIN_ATTEMPTS} '
                        f'failed login attempts ({username})'
                    ),
                    request=self.request, category='auth', outcome='failure',
                    severity='high',
                )
                messages.error(self.request, locked_message(employee))
            else:
                log_audit(
                    user=employee.user, action='login_failed',
                    model_name='Employee', object_id=employee.employee_id,
                    description=f'Failed login for {username}',
                    request=self.request, category='auth', outcome='failure',
                    severity='low',
                )
        else:
            log_audit(
                user=None, action='login_failed',
                model_name='User', object_id=username[:100],
                description=f'Failed login for unknown account "{username}"',
                request=self.request, category='auth', outcome='failure',
                severity='low',
            )
        return super().form_invalid(form)
