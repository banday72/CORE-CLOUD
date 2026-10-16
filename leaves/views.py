from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Leave, LeaveType, LeaveBalance
from .forms import LeaveForm, LeaveTypeForm, LeaveApprovalForm
from employees.views import get_employee
from employees.decorators import permission_required
from employees.ajax import is_ajax, json_ok, json_err
from hr_modules.notify import notify, notify_reports_to


from datetime import date


def _current_balances(employee):
    if not employee:
        return []
    year = date.today().year
    return LeaveBalance.objects.filter(employee=employee, year=year).select_related('leave_type')


@login_required
def leave_list(request):
    employee = get_employee(request.user)
    if employee:
        leaves = Leave.objects.filter(employee=employee)
    else:
        leaves = Leave.objects.all()

    status_filter = request.GET.get('status', '')
    if status_filter:
        leaves = leaves.filter(status=status_filter)

    paginator = Paginator(leaves, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    balances = _current_balances(employee)
    total_allocated = sum(b.allocated for b in balances)
    total_used = sum(b.used for b in balances)

    return render(request, 'leaves/leave_list.html', {
        'leaves': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'is_employee': employee is not None,
        'balances': balances,
        'total_allocated': total_allocated,
        'total_used': total_used,
        'year': date.today().year,
    })


@login_required
def leave_create(request):
    employee = get_employee(request.user)
    if request.method == 'POST':
        form = LeaveForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            if employee:
                leave.employee = employee
                balance = LeaveBalance.objects.filter(
                    employee=employee, leave_type=leave.leave_type,
                    year=leave.start_date.year).first()
                requested = leave.total_days
                if balance and requested > balance.remaining:
                    messages.error(
                        request,
                        f'Insufficient balance for {leave.leave_type.name}: '
                        f'requested {requested} day(s), only {balance.remaining} remaining '
                        f'({balance.allocated} allocated - {balance.used} used).')
                    return render(request, 'leaves/leave_form.html',
                                  {'form': form, 'title': 'Apply for Leave'})
            leave.save()
            messages.success(request, 'Leave request submitted successfully.')
            if employee:
                notify(
                    employee, 'Leave request submitted',
                    f'Your {leave.leave_type.name} leave '
                    f'({leave.start_date} to {leave.end_date}) is awaiting approval.')
                notify_reports_to(
                    employee, 'New leave request',
                    f'{employee.full_name} ({employee.employee_id}) requested '
                    f'{leave.total_days} day(s) of {leave.leave_type.name} '
                    f'from {leave.start_date} to {leave.end_date}.',
                    link='/leaves/')
            return redirect('leave_list')
    else:
        form = LeaveForm()
        if employee:
            form.fields['employee'].initial = employee
            form.fields['employee'].widget = forms.HiddenInput()
    return render(request, 'leaves/leave_form.html', {
        'form': form,
        'title': 'Apply for Leave',
        'balances': _current_balances(employee),
    })


@login_required
@permission_required('manage_leaves')
def leave_approve(request, pk):
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        if is_ajax(request):
            status = request.POST.get('status', '')
            if status not in ('approved', 'rejected'):
                return json_err('Invalid status.')
            leave.status = status
            leave.approved_by = (request.POST.get('approved_by', '').strip()
                                 or request.user.get_full_name()
                                 or request.user.username)
            leave.save()
            notify(
                leave.employee,
                'Leave ' + leave.status,
                f'Your {leave.leave_type.name} leave '
                f'({leave.start_date} to {leave.end_date}) was {leave.status}.',
                'success' if leave.status == 'approved' else 'danger' if leave.status == 'rejected' else 'info')
            badge = {'approved': 'success', 'rejected': 'danger'}.get(leave.status, 'secondary')
            return json_ok(
                f'Leave request {leave.status}.',
                type='success' if leave.status == 'approved' else 'danger',
                status=leave.status,
                status_display=leave.get_status_display(),
                badge=badge)
        form = LeaveApprovalForm(request.POST)
        if form.is_valid():
            leave.status = form.cleaned_data['status']
            leave.approved_by = form.cleaned_data['approved_by']
            leave.save()
            notify(
                leave.employee,
                'Leave ' + leave.status,
                f'Your {leave.leave_type.name} leave '
                f'({leave.start_date} to {leave.end_date}) was {leave.status}.',
                'success' if leave.status == 'approved' else 'danger' if leave.status == 'rejected' else 'info')
            messages.success(request, f'Leave request {leave.status}.')
            return redirect('leave_list')
    else:
        form = LeaveApprovalForm()
    return render(request, 'leaves/leave_approve.html', {'form': form, 'leave': leave})


@login_required
@permission_required('manage_leaves')
def leave_delete(request, pk):
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        leave.delete()
        if is_ajax(request):
            return json_ok('Leave deleted successfully.')
        messages.success(request, 'Leave deleted successfully.')
        return redirect('leave_list')
    return render(request, 'leaves/leave_confirm_delete.html', {'leave': leave})


@login_required
def leave_type_list(request):
    leave_types = LeaveType.objects.all()
    return render(request, 'leaves/leave_type_list.html', {'leave_types': leave_types})


@login_required
@permission_required('manage_leaves')
def leave_type_create(request):
    if request.method == 'POST':
        form = LeaveTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Leave type created successfully.')
            return redirect('leave_type_list')
    else:
        form = LeaveTypeForm()
    return render(request, 'leaves/leave_type_form.html', {'form': form, 'title': 'Add Leave Type'})


from django import forms as django_forms
