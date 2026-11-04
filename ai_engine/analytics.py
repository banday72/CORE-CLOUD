from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict
from django.db.models import Avg, Count, Sum, Q, F, StdDev
from employees.models import Employee, Department
from attendance.models import Attendance
from leaves.models import Leave, LeaveType
from payroll.models import Payroll, PayrollBreakdown, BudgetLoan, BoutiqueIssue


def attendance_analytics(month=None, year=None):
    today = date.today()
    month = month or today.month
    year = year or today.year

    records = Attendance.objects.filter(date__month=month, date__year=year).select_related('employee', 'employee__department')

    emp_stats = defaultdict(lambda: {'present': 0, 'absent': 0, 'late': 0, 'half_day': 0, 'holiday': 0, 'total': 0})
    dept_stats = defaultdict(lambda: {'present': 0, 'absent': 0, 'late': 0, 'half_day': 0, 'holiday': 0, 'total': 0})
    late_pattern = defaultdict(list)
    absent_risk = []

    for r in records:
        emp = r.employee
        emp_stats[emp]['total'] += 1
        emp_stats[emp][r.status] += 1

        dept_name = emp.department.name if emp.department else 'Unassigned'
        dept_stats[dept_name]['total'] += 1
        dept_stats[dept_name][r.status] = dept_stats[dept_name].get(r.status, 0) + 1

        if r.status == 'late' and r.clock_in:
            late_pattern[emp].append(r.clock_in.hour * 60 + r.clock_in.minute)

    insights = []
    risk_employees = []
    top_performers = []

    for emp, stats in emp_stats.items():
        total = stats['total']
        if total == 0:
            continue
        present_pct = ((stats['present'] + stats['late']) / total) * 100
        late_count = stats['late']
        absent_count = stats['absent']

        if present_pct < 70:
            risk_employees.append({
                'employee': emp, 'attendance_pct': round(present_pct, 1),
                'absent_days': absent_count, 'late_days': late_count,
                'risk_level': 'high', 'reason': f'Attendance only {present_pct:.0f}%'
            })
        elif present_pct < 85:
            risk_employees.append({
                'employee': emp, 'attendance_pct': round(present_pct, 1),
                'absent_days': absent_count, 'late_days': late_count,
                'risk_level': 'medium', 'reason': f'Attendance below 85% ({present_pct:.0f}%)'
            })

        if late_count >= 5:
            avg_late_min = sum(late_pattern[emp]) / len(late_pattern[emp]) if late_pattern[emp] else 0
            risk_employees.append({
                'employee': emp, 'attendance_pct': round(present_pct, 1),
                'absent_days': absent_count, 'late_days': late_count,
                'risk_level': 'high', 'reason': f'Late {late_count} times (avg {avg_late_min:.0f} min late)'
            })

        if present_pct >= 95:
            top_performers.append({
                'employee': emp, 'attendance_pct': round(present_pct, 1),
                'late_days': late_count, 'absent_days': absent_count
            })

    top_performers.sort(key=lambda x: x['attendance_pct'], reverse=True)

    total_records = records.count()
    overall_present = records.filter(status__in=['present', 'late']).count()
    overall_late = records.filter(status='late').count()
    overall_absent = records.filter(status='absent').count()
    overall_pct = (overall_present / total_records * 100) if total_records > 0 else 0

    return {
        'month': month, 'year': year,
        'overall': {
            'total_records': total_records,
            'present': overall_present, 'late': overall_late,
            'absent': overall_absent,
            'attendance_pct': round(overall_pct, 1),
        },
        'department_stats': dict(dept_stats),
        'risk_employees': sorted(risk_employees, key=lambda x: {'high': 0, 'medium': 1}.get(x['risk_level'], 2)),
        'top_performers': top_performers[:10],
        'insights': insights,
    }


def payroll_anomaly_detection():
    today = date.today()
    payrolls = Payroll.objects.filter(
        month=today.month, year=today.year
    ).select_related('employee', 'employee__department')

    if not payrolls.exists():
        payrolls = Payroll.objects.select_related('employee', 'employee__department').order_by('-year', '-month')[:50]

    anomalies = []
    if not payrolls.exists():
        return {'anomalies': [], 'summary': {'total_payrolls': 0, 'total_amount': 0, 'anomaly_count': 0}}

    salaries = [float(p.net_salary) for p in payrolls]
    avg_salary = sum(salaries) / len(salaries) if salaries else 0
    std_dev = (sum((s - avg_salary) ** 2 for s in salaries) / len(salaries)) ** 0.5 if len(salaries) > 1 else 0

    for p in payrolls:
        net = float(p.net_salary)
        basic = float(p.basic_salary)

        if p.employee.salary > 0:
            expected_basic = float(p.employee.salary) / 12
            deviation_pct = abs(basic - expected_basic) / expected_basic * 100 if expected_basic > 0 else 0
            if deviation_pct > 20:
                anomalies.append({
                    'employee': p.employee, 'payroll': p,
                    'type': 'salary_mismatch', 'severity': 'high',
                    'description': f'Basic salary Rs. {basic:,.0f} deviates {deviation_pct:.0f}% from expected Rs. {expected_basic:,.0f}',
                    'actual': basic, 'expected': expected_basic,
                })

        if std_dev > 0 and abs(net - avg_salary) > 2 * std_dev:
            anomalies.append({
                'employee': p.employee, 'payroll': p,
                'type': 'outlier', 'severity': 'medium',
                'description': f'Net salary Rs. {net:,.0f} is {abs(net - avg_salary) / std_dev:.1f} std devs from average Rs. {avg_salary:,.0f}',
                'actual': net, 'expected': avg_salary,
            })

        if float(p.allowances) > float(p.basic_salary) * 0.5:
            anomalies.append({
                'employee': p.employee, 'payroll': p,
                'type': 'high_allowance', 'severity': 'medium',
                'description': f'Allowances Rs. {p.allowances:,.0f} exceed 50% of basic salary Rs. {p.basic_salary:,.0f}',
                'actual': float(p.allowances), 'expected': float(p.basic_salary) * 0.5,
            })

        if float(p.deductions) > float(p.basic_salary) * 0.3:
            anomalies.append({
                'employee': p.employee, 'payroll': p,
                'type': 'high_deduction', 'severity': 'high',
                'description': f'Deductions Rs. {p.deductions:,.0f} exceed 30% of basic salary Rs. {p.basic_salary:,.0f}',
                'actual': float(p.deductions), 'expected': float(p.basic_salary) * 0.3,
            })

        if p.net_salary < 0:
            anomalies.append({
                'employee': p.employee, 'payroll': p,
                'type': 'negative_pay', 'severity': 'critical',
                'description': f'Negative net salary Rs. {p.net_salary:,.0f}',
                'actual': float(p.net_salary), 'expected': 0,
            })

    duplicates = Payroll.objects.values('employee', 'month', 'year').annotate(
        cnt=Count('id')).filter(cnt__gt=1)
    for d in duplicates:
        emp = Employee.objects.get(pk=d['employee'])
        anomalies.append({
            'employee': emp, 'payroll': None,
            'type': 'duplicate', 'severity': 'critical',
            'description': f'Duplicate payroll entry for {d["month"]}/{d["year"]}',
            'actual': d['cnt'], 'expected': 1,
        })

    return {
        'anomalies': anomalies,
        'summary': {
            'total_payrolls': len(salaries),
            'total_amount': sum(salaries),
            'avg_salary': round(avg_salary, 2),
            'anomaly_count': len(anomalies),
        }
    }


def employee_risk_prediction():
    today = date.today()
    window_start = today - timedelta(days=90)
    employees = Employee.objects.filter(status='active').select_related('department')

    att_map = {
        row['employee']: row for row in
        Attendance.objects.filter(date__gte=window_start)
        .values('employee')
        .annotate(total=Count('id'),
                  absent=Count('id', filter=Q(status='absent')),
                  late=Count('id', filter=Q(status='late')))
    }
    leave_map = {
        row['employee']: row['c'] for row in
        Leave.objects.filter(status='approved', start_date__gte=window_start)
        .values('employee').annotate(c=Count('id'))
    }
    loan_map = {
        row['employee']: row['c'] for row in
        BudgetLoan.objects.filter(is_active=True).values('employee').annotate(c=Count('id'))
    }

    risk_data = []
    for emp in employees:
        score = 0
        reasons = []

        att = att_map.get(emp.pk)
        if att and att['total']:
            total_att = att['total']
            absent_pct = (att['absent'] / total_att) * 100
            late_pct = (att['late'] / total_att) * 100
            if absent_pct > 20:
                score += 30
                reasons.append(f'High absenteeism ({absent_pct:.0f}%)')
            elif absent_pct > 10:
                score += 15
                reasons.append(f'Moderate absenteeism ({absent_pct:.0f}%)')
            if late_pct > 15:
                score += 20
                reasons.append(f'Frequent lateness ({late_pct:.0f}%)')

        leave_count = leave_map.get(emp.pk, 0)
        if leave_count > 8:
            score += 25
            reasons.append(f'Excessive leaves ({leave_count} in 3 months)')
        elif leave_count > 5:
            score += 10
            reasons.append(f'High leave usage ({leave_count} in 3 months)')

        days_employed = (today - emp.date_of_joining).days
        if days_employed > 365 * 3:
            score += 10
            reasons.append('Long tenure - may seek new opportunities')

        pending_loans = loan_map.get(emp.pk, 0)
        if pending_loans > 0:
            score += 5
            reasons.append('Has active budget loan')

        if emp.salary < 50000:
            score += 15
            reasons.append('Below average salary')

        if score >= 40:
            risk_level = 'high'
        elif score >= 20:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        if reasons:
            risk_data.append({
                'employee': emp, 'score': min(score, 100),
                'risk_level': risk_level, 'reasons': reasons,
                'days_employed': days_employed,
                'approved_leaves': leave_count,
            })

    risk_data.sort(key=lambda x: x['score'], reverse=True)
    return {'risks': risk_data}


def salary_recommendations():
    today = date.today()
    employees = Employee.objects.filter(status='active').select_related('department')

    recommendations = []
    dept_salaries = defaultdict(list)

    for emp in employees:
        if emp.department:
            dept_salaries[emp.department.name].append(float(emp.salary))

    dept_avg = {dept: sum(salaries) / len(salaries) for dept, salaries in dept_salaries.items()}

    for emp in employees:
        if not emp.department or emp.department.name not in dept_avg:
            continue

        avg = dept_avg[emp.department.name]
        current = float(emp.salary)
        diff_pct = ((current - avg) / avg * 100) if avg > 0 else 0

        rec_type = None
        suggested = None
        priority = None

        if diff_pct < -20:
            rec_type = 'increase'
            suggested = round(avg * 1.10, -2)
            priority = 'high'
        elif diff_pct < -10:
            rec_type = 'increase'
            suggested = round(avg * 1.05, -2)
            priority = 'medium'
        elif diff_pct > 30:
            rec_type = 'review'
            suggested = round(avg * 1.15, -2)
            priority = 'medium'
        elif diff_pct > 20:
            rec_type = 'review'
            suggested = round(avg * 1.10, -2)
            priority = 'low'

        if rec_type:
            recommendations.append({
                'employee': emp, 'current_salary': current,
                'dept_average': round(avg, 2), 'diff_pct': round(diff_pct, 1),
                'recommendation': rec_type, 'suggested': suggested,
                'priority': priority,
            })

    recommendations.sort(key=lambda x: abs(x['diff_pct']), reverse=True)
    return {
        'recommendations': recommendations,
        'dept_averages': dept_avg,
    }


def natural_language_report(query):
    query_lower = query.lower().strip()
    today = date.today()
    result = {'query': query, 'type': 'unknown', 'data': None, 'message': ''}

    if any(w in query_lower for w in ['salary', 'pay', 'payroll', 'payslip']):
        month = today.month
        year = today.year
        for m_name, m_num in [('jan', 1), ('feb', 2), ('mar', 3), ('apr', 4), ('may', 5), ('jun', 6),
                               ('jul', 7), ('aug', 8), ('sep', 9), ('oct', 10), ('nov', 11), ('dec', 12)]:
            if m_name in query_lower:
                month = m_num
                break

        dept = None
        for d in Department.objects.all():
            if d.name.lower() in query_lower:
                dept = d
                break

        payrolls = Payroll.objects.filter(month=month, year=year).select_related('employee', 'employee__department')
        if dept:
            payrolls = payrolls.filter(employee__department=dept)

        total = payrolls.aggregate(total=Sum('net_salary'), avg=Avg('net_salary'), count=Count('id'))
        result['type'] = 'payroll_report'
        result['data'] = {
            'payrolls': list(payrolls.values('employee__employee_id', 'employee__first_name', 'employee__last_name', 'net_salary', 'status')),
            'summary': total,
            'month': month, 'year': year,
            'department': dept.name if dept else 'All',
        }
        dept_text = f" in {dept.name}" if dept else ""
        result['message'] = f'Payroll report for {date(year, month, 1).strftime("%B %Y")}{dept_text}: {total["count"]} records, Total: Rs. {total["total"] or 0:,.2f}, Average: Rs. {total["avg"] or 0:,.2f}'

    elif any(w in query_lower for w in ['attendance', 'present', 'absent', 'late']):
        month = today.month
        year = today.year
        for m_name, m_num in [('jan', 1), ('feb', 2), ('mar', 3), ('apr', 4), ('may', 5), ('jun', 6),
                               ('jul', 7), ('aug', 8), ('sep', 9), ('oct', 10), ('nov', 11), ('dec', 12)]:
            if m_name in query_lower:
                month = m_num
                break

        records = Attendance.objects.filter(date__month=month, date__year=year)
        stats = {
            'total': records.count(),
            'present': records.filter(status='present').count(),
            'absent': records.filter(status='absent').count(),
            'late': records.filter(status='late').count(),
            'half_day': records.filter(status='half_day').count(),
        }
        result['type'] = 'attendance_report'
        result['data'] = stats
        result['message'] = f'Attendance for {date(year, month, 1).strftime("%B %Y")}: {stats["total"]} records. Present: {stats["present"]}, Absent: {stats["absent"]}, Late: {stats["late"]}'

    elif any(w in query_lower for w in ['leave', 'leaves', 'holiday']):
        pending = Leave.objects.filter(status='pending').count()
        approved = Leave.objects.filter(status='approved').count()
        rejected = Leave.objects.filter(status='rejected').count()
        result['type'] = 'leave_report'
        result['data'] = {'pending': pending, 'approved': approved, 'rejected': rejected}
        result['message'] = f'Leave summary: {pending} pending, {approved} approved, {rejected} rejected'

    elif any(w in query_lower for w in ['employee', 'staff', 'team', 'headcount']):
        active = Employee.objects.filter(status='active').count()
        inactive = Employee.objects.filter(status='inactive').count()
        terminated = Employee.objects.filter(status='terminated').count()
        by_dept = dict(Employee.objects.filter(status='active').values_list('department__name').annotate(c=Count('id')).values_list('name', 'c'))
        result['type'] = 'employee_report'
        result['data'] = {'active': active, 'inactive': inactive, 'terminated': terminated, 'by_department': by_dept}
        result['message'] = f'Headcount: {active} active, {inactive} inactive, {terminated} terminated'

    elif any(w in query_lower for w in ['department', 'dept']):
        depts = Department.objects.annotate(emp_count=Count('employee')).order_by('-emp_count')
        dept_list = [{'name': d.name, 'count': d.emp_count} for d in depts]
        result['type'] = 'department_report'
        result['data'] = dept_list
        result['message'] = f'Departments: {", ".join(f"{d["name"]} ({d["count"]})" for d in dept_list)}'

    elif any(w in query_lower for w in ['loan', 'budget']):
        active_loans = BudgetLoan.objects.filter(is_active=True)
        total_loan = active_loans.aggregate(total=Sum('loan_amount'), remaining=Sum('remaining_amount'))
        result['type'] = 'loan_report'
        result['data'] = {'active_count': active_loans.count(), **total_loan}
        result['message'] = f'Budget loans: {active_loans.count()} active, Total: Rs. {total_loan["total"] or 0:,.2f}, Remaining: Rs. {total_loan["remaining"] or 0:,.2f}'

    elif any(w in query_lower for w in ['boutique', 'product', 'issue']):
        products = BoutiqueIssue.objects.select_related('product', 'employee')
        total_issues = products.aggregate(total=Sum('total_price'), count=Count('id'))
        result['type'] = 'boutique_report'
        result['data'] = total_issues
        result['message'] = f'Boutique: {total_issues["count"]} items issued, Total value: Rs. {total_issues["total"] or 0:,.2f}'

    elif any(w in query_lower for w in ['hello', 'hi', 'hey', 'help']):
        result['type'] = 'help'
        result['message'] = 'I can help with:\n- "Show salary for March"\n- "Attendance report"\n- "How many employees?"\n- "Leave summary"\n- "Department headcount"\n- "Budget loans"\n- "Boutique items"'

    else:
        result['message'] = f'I understand queries about: salary, attendance, employees, leaves, departments, loans, boutique. Try: "Show salary for September" or "How many active employees?"'

    return result


def chatbot_response(message, user=None):
    msg = message.lower().strip()
    today = date.today()

    if user and hasattr(user, 'employee'):
        emp = user.employee
        if any(w in msg for w in ['my salary', 'my pay', 'my payslip', 'how much do i earn']):
            latest = Payroll.objects.filter(employee=emp).order_by('-year', '-month').first()
            if latest:
                return f'Your latest payslip ({latest.get_month_display()} {latest.year}):\nBasic: Rs. {latest.basic_salary:,.2f}\nAllowances: Rs. {latest.allowances:,.2f}\nDeductions: Rs. {latest.deductions:,.2f}\nTax: Rs. {latest.tax:,.2f}\nNet Salary: Rs. {latest.net_salary:,.2f}\nStatus: {latest.get_status_display()}'
            return 'No payroll records found for you yet.'

        if any(w in msg for w in ['my attendance', 'my attendance', 'am i present', 'clock in']):
            today_att = Attendance.objects.filter(employee=emp, date=today).first()
            if today_att:
                status = f'Status: {today_att.get_status_display()}'
                if today_att.clock_in:
                    status += f'\nClock In: {today_att.clock_in.strftime("%H:%M")}'
                if today_att.clock_out:
                    status += f'\nClock Out: {today_att.clock_out.strftime("%H:%M")}'
                return status
            return 'No attendance record for today. Click Clock In to mark your attendance.'

        if any(w in msg for w in ['my leave', 'my leaves', 'leave balance', 'how many leaves']):
            approved = Leave.objects.filter(employee=emp, status='approved').count()
            pending = Leave.objects.filter(employee=emp, status='pending').count()
            return f'Your leave status:\nApproved: {approved}\nPending: {pending}'

    if any(w in msg for w in ['hello', 'hi', 'hey', 'good morning', 'good evening']):
        name = ''
        if user and hasattr(user, 'employee'):
            name = f' {user.employee.first_name}'
        elif user and user.is_superuser:
            name = ' Sir/Ma\'am'
        return f'Hello{name}! I am your HR AI Assistant. Ask me about salary, attendance, leaves, employees, or departments.'

    if any(w in msg for w in ['help', 'what can you do', 'commands', 'options']):
        return ('I can help with:\n\n'
                '- "How many employees?"\n'
                '- "Show salary for September"\n'
                '- "Attendance report"\n'
                - '"Leave summary"\n'
                '- "Department headcount"\n'
                '- "Budget loans"\n'
                '- "Who is late today?"\n'
                '- "Top performers"\n'
                '- "Show [employee name]"')

    if any(w in msg for w in ['how many employee', 'total employee', 'headcount', 'employee count']):
        active = Employee.objects.filter(status='active').count()
        return f'Total active employees: {active}'

    if any(w in msg for w in ['department', 'dept']):
        depts = Department.objects.annotate(emp_count=Count('employee')).order_by('-emp_count')
        lines = [f'{d.name}: {d.emp_count} employees' for d in depts]
        return 'Department headcount:\n' + '\n'.join(lines) if lines else 'No departments found.'

    if any(w in msg for w in ['leave summary', 'pending leave', 'leave request']):
        pending = Leave.objects.filter(status='pending').count()
        approved = Leave.objects.filter(status='approved').count()
        rejected = Leave.objects.filter(status='rejected').count()
        return f'Leave summary:\nPending: {pending}\nApproved: {approved}\nRejected: {rejected}'

    if any(w in msg for w in ['loan', 'budget loan']):
        active = BudgetLoan.objects.filter(is_active=True)
        total = active.aggregate(Sum('loan_amount'), Sum('remaining_amount'))
        return f'Active loans: {active.count()}\nTotal loan: Rs. {total["loan_amount__sum"] or 0:,.2f}\nRemaining: Rs. {total["remaining_amount__sum"] or 0:,.2f}'

    if any(w in msg for w in ['salary', 'pay']):
        month = today.month
        year = today.year
        for m_name, m_num in [('jan', 1), ('feb', 2), ('mar', 3), ('apr', 4), ('may', 5), ('jun', 6),
                               ('jul', 7), ('aug', 8), ('sep', 9), ('oct', 10), ('nov', 11), ('dec', 12)]:
            if m_name in msg:
                month = m_num
                break
        payrolls = Payroll.objects.filter(month=month, year=year)
        total = payrolls.aggregate(Sum('net_salary'), Avg('net_salary'), Count('id'))
        return f'Payroll for {date(year, month, 1).strftime("%B %Y")}:\nRecords: {total["id__count"]}\nTotal: Rs. {total["net_salary__sum"] or 0:,.2f}\nAverage: Rs. {total["net_salary__avg"] or 0:,.2f}'

    if any(w in msg for w in ['attendance', 'present', 'absent']):
        month = today.month
        year = today.year
        for m_name, m_num in [('jan', 1), ('feb', 2), ('mar', 3), ('apr', 4), ('may', 5), ('jun', 6),
                               ('jul', 7), ('aug', 8), ('sep', 9), ('oct', 10), ('nov', 11), ('dec', 12)]:
            if m_name in msg:
                month = m_num
                break
        records = Attendance.objects.filter(date__month=month, date__year=year)
        return (f'Attendance for {date(year, month, 1).strftime("%B %Y")}:\n'
                f'Present: {records.filter(status="present").count()}\n'
                f'Absent: {records.filter(status="absent").count()}\n'
                f'Late: {records.filter(status="late").count()}\n'
                f'Half Day: {records.filter(status="half_day").count()}')

    if 'late' in msg:
        late_today = Attendance.objects.filter(date=today, status='late').select_related('employee')
        if late_today.exists():
            names = [f'{a.employee.employee_id} - {a.employee.full_name} ({a.clock_in.strftime("%H:%M") if a.clock_in else "N/A"})' for a in late_today]
            return f'Late employees today ({late_today.count()}):\n' + '\n'.join(names)
        return 'No one is late today!'

    return ('I can help with:\n'
            '- "How many employees?"\n'
            '- "Show salary for September"\n'
            '- "Attendance report"\n'
            '- "Leave summary"\n'
            '- "Department headcount"\n'
            '- "Budget loans"\n'
            '- "Who is late today?"\n'
            '- "My salary" (for your payslip)\n'
            '- "My attendance" (for today)')
