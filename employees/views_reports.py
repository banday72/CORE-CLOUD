import csv
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse
from django.shortcuts import render

from employees.models import Employee
from employees.decorators import permission_required
from leaves.models import Leave, LeaveType
from attendance.models import Attendance
from payroll.models import Payroll


def _audit_export(request, model_name, count):
    from employees.audit import log_audit
    log_audit(
        user=request.user, action='export', model_name=model_name,
        object_id=model_name,
        description=f'Exported {count} {model_name} records to CSV',
        request=request, category='data', severity='low',
    )


@login_required
@permission_required('view_reports')
def reports_dashboard(request):
    today = date.today()

    active = Employee.objects.filter(status='active')

    headcount = list(
        active.values('department__name')
        .annotate(value=Count('id'))
        .order_by('-value')
    )
    for row in headcount:
        row['label'] = row.pop('department__name') or 'No Dept'

    salary_cost = list(
        active.values('department__name')
        .annotate(value=Sum('salary'))
        .order_by('-value')
    )
    for row in salary_cost:
        row['label'] = row.pop('department__name') or 'No Dept'
        row['value'] = float(row['value'] or 0)

    dept_avg = list(
        active.values('department__name')
        .annotate(value=Avg('salary'))
        .order_by('-value')
    )
    for row in dept_avg:
        row['label'] = row.pop('department__name') or 'No Dept'
        row['value'] = round(float(row['value'] or 0), 2)

    payroll_months = []
    for i in range(5, -1, -1):
        d = today.replace(day=1) - timedelta(days=28 * i)
        total = Payroll.objects.filter(
            month=d.month, year=d.year, status__in=['processed', 'paid']
        ).aggregate(s=Sum('net_salary'))['s'] or 0
        payroll_months.append({'label': d.strftime('%b %y'), 'value': float(total)})

    attendance_trend = []
    trend_start = today - timedelta(days=13)
    trend_rows = (
        Attendance.objects.filter(date__gte=trend_start, date__lte=today)
        .values('date', 'status').annotate(c=Count('id'))
    )
    trend_map = {}
    for row in trend_rows:
        trend_map.setdefault(row['date'], {})[row['status']] = row['c']
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        counts = trend_map.get(d, {})
        attendance_trend.append({
            'label': d.strftime('%d %b'),
            'present': counts.get('present', 0) + counts.get('late', 0),
            'absent': counts.get('absent', 0),
            'half_day': counts.get('half_day', 0),
        })

    leaves_by_type = list(
        Leave.objects.filter(status='approved', start_date__year=today.year)
        .values('leave_type__name')
        .annotate(value=Count('id'))
        .order_by('-value')
    )
    for row in leaves_by_type:
        row['label'] = row.pop('leave_type__name')
    if not leaves_by_type:
        leaves_by_type = [{'label': lt.name, 'value': 0} for lt in LeaveType.objects.all()]

    upcoming_birthdays = Employee.objects.filter(
        status='active',
        date_of_birth__isnull=False,
    ).select_related('department').order_by('date_of_birth')[:100]
    bday_list = []
    for e in upcoming_birthdays:
        try:
            next_bday = e.date_of_birth.replace(year=today.year)
        except ValueError:
            next_bday = e.date_of_birth.replace(year=today.year, day=28)
        if next_bday < today:
            next_bday = next_bday.replace(year=today.year + 1)
        delta = (next_bday - today).days
        if delta <= 30:
            bday_list.append({
                'name': e.full_name,
                'employee_id': e.employee_id,
                'department': e.department.name if e.department else '',
                'next_birthday': next_bday,
                'days': delta,
                'today': delta == 0,
            })
    bday_list.sort(key=lambda x: x['days'])

    top_earners = list(
        active.order_by('-salary')[:5]
        .values('employee_id', 'first_name', 'last_name', 'salary', 'designation')
    )

    month_total = sum(pm['value'] for pm in payroll_months)
    active_count = active.count()
    avg_salary = active.aggregate(a=Avg('salary'))['a'] or 0
    pending_leaves = Leave.objects.filter(status='pending').count()
    approved_leave_days = sum(
        (l.end_date - l.start_date).days + 1
        for l in Leave.objects.filter(status='approved', start_date__year=today.year)
    )

    return render(request, 'reports/reports_dashboard.html', {
        'headcount': headcount,
        'salary_cost': salary_cost,
        'dept_avg': dept_avg,
        'payroll_months': payroll_months,
        'attendance_trend': attendance_trend,
        'leaves_by_type': leaves_by_type,
        'birthdays': bday_list,
        'top_earners': top_earners,
        'active_count': active_count,
        'avg_salary': round(float(avg_salary), 2),
        'month_total': round(month_total, 2),
        'pending_leaves': pending_leaves,
        'approved_leave_days': approved_leave_days,
    })


@login_required
@permission_required('view_reports')
def export_employees_csv(request):
    rows = list(Employee.objects.select_related('department', 'reports_to')
                .order_by('employee_id'))
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="employees.csv"'
    writer = csv.writer(response)
    writer.writerow(['Employee ID', 'Name', 'Email', 'Department', 'Designation',
                     'Salary', 'Status', 'Role', 'Manager'])
    for e in rows:
        writer.writerow([
            e.employee_id, e.full_name, e.email,
            e.department.name if e.department else '',
            e.designation, e.salary, e.status, e.role,
            e.reports_to.employee_id if e.reports_to else '',
        ])
    _audit_export(request, 'Employee', len(rows))
    return response


@login_required
@permission_required('manage_attendance')
def export_attendance_csv(request):
    rows = list(Attendance.objects.select_related('employee').order_by('-date'))
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="attendance.csv"'
    writer = csv.writer(response)
    writer.writerow(['Employee ID', 'Name', 'Date', 'Status', 'Clock In', 'Clock Out'])
    for a in rows:
        writer.writerow([
            a.employee.employee_id, a.employee.full_name,
            a.date.isoformat(), a.status,
            a.clock_in.strftime('%H:%M') if a.clock_in else '',
            a.clock_out.strftime('%H:%M') if a.clock_out else '',
        ])
    _audit_export(request, 'Attendance', len(rows))
    return response


@login_required
@permission_required('view_reports')
def export_payroll_csv(request):
    rows = list(Payroll.objects.select_related('employee').order_by('-year', '-month'))
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payroll.csv"'
    writer = csv.writer(response)
    writer.writerow(['Employee ID', 'Name', 'Month', 'Year', 'Basic', 'Allowances',
                     'Deductions', 'Tax', 'Net', 'Status'])
    for p in rows:
        writer.writerow([
            p.employee.employee_id, p.employee.full_name,
            p.get_month_display(), p.year, p.basic_salary, p.allowances,
            p.deductions, p.tax, p.net_salary, p.status,
        ])
    _audit_export(request, 'Payroll', len(rows))
    return response