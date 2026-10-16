from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from datetime import date, datetime
from .models import Attendance
from .forms import AttendanceForm, AttendanceFilterForm
from employees.views import get_employee
from employees.decorators import permission_required
from employees.ajax import is_ajax, json_ok, json_err


@login_required
def attendance_list(request):
    employee = get_employee(request.user)
    if employee:
        attendance = Attendance.objects.filter(employee=employee)
    else:
        form = AttendanceFilterForm(request.GET)
        attendance = Attendance.objects.all()
        if form.is_valid():
            if form.cleaned_data.get('date_from'):
                attendance = attendance.filter(date__gte=form.cleaned_data['date_from'])
            if form.cleaned_data.get('date_to'):
                attendance = attendance.filter(date__lte=form.cleaned_data['date_to'])
            if form.cleaned_data.get('employee'):
                attendance = attendance.filter(employee__employee_id__icontains=form.cleaned_data['employee'])
            if form.cleaned_data.get('status'):
                attendance = attendance.filter(status=form.cleaned_data['status'])

    paginator = Paginator(attendance, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {
        'attendance': page_obj,
        'page_obj': page_obj,
        'is_employee': employee is not None,
    }
    if not employee:
        ctx['filter_form'] = AttendanceFilterForm(request.GET)
    return render(request, 'attendance/attendance_list.html', ctx)


@login_required
def attendance_clock_in(request):
    employee = get_employee(request.user)
    if not employee:
        if is_ajax(request):
            return json_err('No employee profile found.')
        messages.error(request, 'No employee profile found.')
        return redirect('dashboard')

    today = date.today()
    existing = Attendance.objects.filter(employee=employee, date=today).first()
    clock_in_time = None
    if existing:
        if existing.clock_in is None:
            existing.clock_in = datetime.now().time()
            existing.status = 'present'
            existing.save()
            clock_in_time = existing.clock_in
            msg = f'Clocked in at {existing.clock_in.strftime("%H:%M")}'
            level = 'success'
        else:
            clock_in_time = existing.clock_in
            msg = 'Already clocked in today.'
            level = 'info'
    else:
        now = datetime.now().time()
        status = 'late' if now.hour > 9 or (now.hour == 9 and now.minute > 0) else 'present'
        Attendance.objects.create(
            employee=employee,
            date=today,
            clock_in=now,
            status=status,
        )
        clock_in_time = now
        msg = f'Clocked in at {now.strftime("%H:%M")}'
        level = 'success'
        if status == 'late':
            msg += ' (Late arrival)'
            level = 'warning'

    if is_ajax(request):
        return json_ok(msg, type=level, clock_in=(clock_in_time.strftime("%H:%M") if clock_in_time else None))
    if level == 'info':
        messages.info(request, msg)
    elif level == 'warning':
        messages.warning(request, msg)
    else:
        messages.success(request, msg)
    return redirect('attendance_list')


@login_required
def attendance_clock_out(request):
    employee = get_employee(request.user)
    if not employee:
        if is_ajax(request):
            return json_err('No employee profile found.')
        messages.error(request, 'No employee profile found.')
        return redirect('dashboard')

    today = date.today()
    existing = Attendance.objects.filter(employee=employee, date=today).first()
    if existing and existing.clock_in and not existing.clock_out:
        existing.clock_out = datetime.now().time()
        existing.save()
        msg = f'Clocked out at {existing.clock_out.strftime("%H:%M")}'
        level = 'success'
    elif existing and existing.clock_out:
        msg = 'Already clocked out today.'
        level = 'info'
    else:
        msg = 'No clock-in record found for today.'
        level = 'warning'

    if is_ajax(request):
        return json_ok(msg, type=level, clock_out=(existing.clock_out.strftime("%H:%M") if existing and existing.clock_out else None))
    if level == 'info':
        messages.info(request, msg)
    elif level == 'warning':
        messages.warning(request, msg)
    else:
        messages.success(request, msg)
    return redirect('attendance_list')


@login_required
@permission_required('manage_attendance')
def attendance_create(request):
    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attendance record created successfully.')
            return redirect('attendance_list')
    else:
        form = AttendanceForm()
    return render(request, 'attendance/attendance_form.html', {'form': form, 'title': 'Add Attendance'})


@login_required
@permission_required('manage_attendance')
def attendance_update(request, pk):
    attendance = get_object_or_404(Attendance, pk=pk)
    if request.method == 'POST':
        form = AttendanceForm(request.POST, instance=attendance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attendance updated successfully.')
            return redirect('attendance_list')
    else:
        form = AttendanceForm(instance=attendance)
    return render(request, 'attendance/attendance_form.html', {'form': form, 'title': 'Edit Attendance'})


@login_required
@permission_required('manage_attendance')
def attendance_delete(request, pk):
    attendance = get_object_or_404(Attendance, pk=pk)
    if request.method == 'POST':
        attendance.delete()
        if is_ajax(request):
            return json_ok('Attendance deleted successfully.')
        messages.success(request, 'Attendance deleted successfully.')
        return redirect('attendance_list')
    return render(request, 'attendance/attendance_confirm_delete.html', {'attendance': attendance})
