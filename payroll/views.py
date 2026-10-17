from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Avg, Q
from decimal import Decimal
from datetime import datetime, date
from calendar import monthrange
import csv
from employees.decorators import permission_required
from employees.ajax import is_ajax, json_ok, json_err
from .models import Payroll, PayrollPolicy, PayrollBreakdown, BoutiqueProduct, BoutiqueIssue, BudgetLoan
from .forms import PayrollForm, PayrollFilterForm, PayrollPolicyForm, BoutiqueProductForm, BoutiqueIssueForm, BudgetLoanForm
from employees.models import Employee, Department, managers_q
from employees.views import get_employee
from attendance.models import Attendance
from leaves.models import Leave


def get_active_policy():
    policy = PayrollPolicy.objects.filter(is_active=True).first()
    if not policy:
        policy = PayrollPolicy.objects.create(name='Default Policy')
    return policy


def calculate_auto_payroll(employee, month, year, policy):
    D = Decimal
    working_days = D(str(policy.working_days_per_month))
    salary = D(str(employee.salary))
    per_day_salary = salary / working_days

    start_date = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = date(year, month, last_day)

    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=start_date,
        date__lte=end_date
    )

    days_present = D(str(attendance_records.filter(status='present').count()))
    days_half_day = D(str(attendance_records.filter(status='half_day').count()))
    days_late = D(str(attendance_records.filter(status='late').count()))
    days_holiday = D(str(attendance_records.filter(status='holiday').count()))

    approved_leaves = Leave.objects.filter(
        employee=employee,
        status='approved',
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    days_approved_leave = D(str(sum(
        min((min(l.end_date, end_date) - max(l.start_date, start_date)).days + 1, int(working_days))
        for l in approved_leaves
    )))

    days_absent = working_days - days_present - days_half_day - days_holiday - days_approved_leave
    if days_absent < 0:
        days_absent = D('0')

    total_present_equiv = days_present + (days_half_day * D('0.5')) + days_holiday + days_approved_leave

    if working_days > 0:
        attendance_pct = (total_present_equiv / working_days) * D('100')
    else:
        attendance_pct = D('0')

    basic_earned = total_present_equiv * per_day_salary

    half_day_deduction = days_half_day * per_day_salary * (D(str(policy.half_day_deduction_percent)) / D('100'))

    absent_deduction = D('0')
    if days_absent > 0:
        if policy.use_per_day_salary_for_absent:
            absent_deduction = days_absent * per_day_salary
        else:
            absent_deduction = days_absent * D(str(policy.absent_deduction_per_day))

    attendance_deduction = half_day_deduction + absent_deduction

    late_deduction = D('0')
    if int(days_late) > policy.late_allowed_per_month:
        extra_late = D(str(int(days_late) - policy.late_allowed_per_month))
        late_deduction = extra_late * D(str(policy.late_deduction_amount))

    performance_bonus = D('0')
    bonus_pct = 0
    if policy.performance_bonus_enabled:
        if attendance_pct >= 100:
            bonus_pct = policy.bonus_100_percent
        elif attendance_pct >= 95:
            bonus_pct = policy.bonus_95_percent
        elif attendance_pct >= 90:
            bonus_pct = policy.bonus_90_percent
        else:
            bonus_pct = policy.bonus_below_90_percent
        performance_bonus = salary * (D(str(bonus_pct)) / D('100'))

    medical = D(str(policy.medical_allowance))
    transport = D(str(policy.transport_allowance))
    house = salary * (D(str(policy.house_allowance_percent)) / D('100'))
    total_allowances = medical + transport + house + performance_bonus

    gross_salary = basic_earned + total_allowances

    boutique_issues = BoutiqueIssue.objects.filter(employee=employee, is_deducted=False)
    boutique_deduction = D(str(sum(issue.total_price for issue in boutique_issues)))

    active_loans = BudgetLoan.objects.filter(employee=employee, is_active=True)
    loan_deduction = D('0')
    for loan in active_loans:
        if loan.remaining_amount > 0:
            deduction = min(loan.monthly_deduction, loan.remaining_amount)
            loan_deduction += deduction

    total_deductions = attendance_deduction + late_deduction + boutique_deduction + loan_deduction
    taxable = gross_salary - total_deductions
    tax = taxable * (D(str(policy.tax_rate_percent)) / D('100'))

    net_salary = gross_salary - total_deductions - tax

    boutique_list = []
    for issue in boutique_issues:
        boutique_list.append({'item_name': issue.product.name, 'amount': issue.total_price})

    loan_list = []
    for loan in active_loans:
        if loan.remaining_amount > 0:
            deduction = min(loan.monthly_deduction, loan.remaining_amount)
            loan_list.append({'reason': loan.reason, 'amount': deduction})

    return {
        'basic_salary': salary,
        'allowances': total_allowances.quantize(D('0.01')),
        'deductions': (total_deductions + tax).quantize(D('0.01')),
        'tax': tax.quantize(D('0.01')),
        'net_salary': max(net_salary, D('0')).quantize(D('0.01')),
        'boutique_items': boutique_issues,
        'active_loans': active_loans,
        'boutique_deduction': boutique_deduction.quantize(D('0.01')),
        'loan_deduction': loan_deduction.quantize(D('0.01')),
        'breakdown': {
            'total_working_days': int(working_days),
            'days_present': int(days_present),
            'days_absent': int(days_absent),
            'days_half_day': int(days_half_day),
            'days_late': int(days_late),
            'days_holiday': int(days_holiday),
            'days_approved_leave': int(days_approved_leave),
            'per_day_salary': per_day_salary.quantize(D('0.01')),
            'basic_earned': basic_earned.quantize(D('0.01')),
            'attendance_deduction': attendance_deduction.quantize(D('0.01')),
            'late_deduction': late_deduction.quantize(D('0.01')),
            'performance_bonus': performance_bonus.quantize(D('0.01')),
            'bonus_percentage': bonus_pct,
            'medical_allowance': medical,
            'transport_allowance': transport,
            'house_allowance': house.quantize(D('0.01')),
            'total_allowances_computed': total_allowances.quantize(D('0.01')),
            'tax_computed': tax.quantize(D('0.01')),
            'attendance_percentage': attendance_pct.quantize(D('0.01')),
        }
    }


@login_required
def payroll_list(request):
    employee = get_employee(request.user)
    if employee:
        payrolls = Payroll.objects.filter(employee=employee).select_related('employee')
    else:
        form = PayrollFilterForm(request.GET)
        payrolls = Payroll.objects.select_related('employee').all()
        if form.is_valid():
            if form.cleaned_data.get('month'):
                payrolls = payrolls.filter(month=form.cleaned_data['month'])
            if form.cleaned_data.get('year'):
                payrolls = payrolls.filter(year=form.cleaned_data['year'])
            if form.cleaned_data.get('status'):
                payrolls = payrolls.filter(status=form.cleaned_data['status'])
    payrolls = payrolls.order_by('-year', '-month', '-id')

    paginator = Paginator(payrolls, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = {
        'payrolls': page_obj,
        'page_obj': page_obj,
        'is_employee': employee is not None,
    }
    if not employee:
        ctx['filter_form'] = PayrollFilterForm(request.GET)
    return render(request, 'payroll/payroll_list.html', ctx)


@login_required
def payroll_create(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.calculate_net_salary()
            payroll.save()
            messages.success(request, 'Payroll record created successfully.')
            return redirect('payroll_list')
    else:
        form = PayrollForm()
    return render(request, 'payroll/payroll_form.html', {'form': form, 'title': 'Create Payroll'})


@login_required
def payroll_detail(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    breakdown = None
    try:
        breakdown = payroll.breakdown
    except PayrollBreakdown.DoesNotExist:
        pass
    return render(request, 'payroll/payroll_detail.html', {'payroll': payroll, 'breakdown': breakdown})


@login_required
def payroll_update(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        form = PayrollForm(request.POST, instance=payroll)
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.calculate_net_salary()
            payroll.save()
            messages.success(request, 'Payroll updated successfully.')
            return redirect('payroll_detail', pk=pk)
    else:
        form = PayrollForm(instance=payroll)
    return render(request, 'payroll/payroll_form.html', {'form': form, 'title': 'Edit Payroll'})


@login_required
@permission_required('manage_payroll')
def payroll_delete(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        payroll.delete()
        if is_ajax(request):
            return json_ok('Payroll deleted successfully.')
        messages.success(request, 'Payroll deleted successfully.')
        return redirect('payroll_list')
    return render(request, 'payroll/payroll_confirm_delete.html', {'payroll': payroll})


@login_required
def payroll_process(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        payroll.status = 'processed'
        payroll.payment_date = datetime.now().date()
        payroll.save()
        from hr_modules.notify import notify
        notify(payroll.employee,
               'Payroll processed',
               f'Your salary for {payroll.get_month_display()} {payroll.year} '
               f'has been processed (Net: ${payroll.net_salary}).',
               'success', 'salary_slip')
        messages.success(request, 'Payroll processed successfully.')
        return redirect('payroll_list')
    return render(request, 'payroll/payroll_confirm_process.html', {'payroll': payroll})


@login_required
def payroll_export(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payroll_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Employee ID', 'Name', 'Month', 'Year', 'Basic Salary',
                     'Allowances', 'Deductions', 'Tax', 'Net Salary', 'Status', 'Type'])

    for payroll in Payroll.objects.all():
        writer.writerow([
            payroll.employee.employee_id,
            payroll.employee.full_name,
            payroll.get_month_display(),
            payroll.year,
            payroll.basic_salary,
            payroll.allowances,
            payroll.deductions,
            payroll.tax,
            payroll.net_salary,
            payroll.get_status_display(),
            payroll.get_generated_type_display(),
        ])

    return response


@login_required
@permission_required('view_reports')
def payroll_summary(request):
    current_year = datetime.now().year
    monthly_summary = Payroll.objects.filter(year=current_year).values('month').annotate(
        total_salary=Sum('net_salary'),
        employee_count=Count('employee', distinct=True),
        avg_salary=Avg('net_salary'),
    ).order_by('month')

    total_employees_on_payroll = Payroll.objects.filter(year=current_year).values('employee').distinct().count()
    grand_total = Payroll.objects.filter(year=current_year).aggregate(total=Sum('net_salary'))['total'] or 0

    return render(request, 'payroll/payroll_summary.html', {
        'monthly_summary': monthly_summary,
        'year': current_year,
        'total_employees_on_payroll': total_employees_on_payroll,
        'grand_total': grand_total,
    })


@login_required
def salary_slip(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    breakdown = None
    try:
        breakdown = payroll.breakdown
    except PayrollBreakdown.DoesNotExist:
        pass
    return render(request, 'payroll/salary_slip.html', {'payroll': payroll, 'breakdown': breakdown})


@login_required
def salary_slip_pdf(request, pk):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    payroll = get_object_or_404(Payroll, pk=pk)
    employee = payroll.employee
    breakdown = None
    try:
        breakdown = payroll.breakdown
    except PayrollBreakdown.DoesNotExist:
        pass

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="salary_slip_{employee.employee_id}_{payroll.month}_{payroll.year}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=20, spaceAfter=6)
    elements.append(Paragraph("SALARY SLIP", title_style))
    elements.append(Paragraph(f"Pay Period: {payroll.get_month_display()} {payroll.year}", styles['Heading3']))
    if payroll.generated_type == 'auto':
        elements.append(Paragraph("<i>Auto-Generated based on Attendance &amp; Leave Policy</i>", styles['Normal']))
    elements.append(Spacer(1, 20))

    header_data = [
        ['Employee Details', '', 'Company Details', ''],
        ['Name:', employee.full_name, 'Company:', 'CoreCloud'],
        ['ID:', employee.employee_id, 'Department:', str(employee.department or 'N/A')],
        ['Designation:', employee.designation or 'N/A', 'Date:', payroll.payment_date.strftime('%d %b %Y') if payroll.payment_date else 'Pending'],
        ['Joining Date:', employee.date_of_joining.strftime('%d %b %Y'), '', ''],
    ]

    header_table = Table(header_data, colWidths=[80, 150, 80, 150])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4e73df')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (2, 0), (3, 0)),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f0f2f7')),
        ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#f0f2f7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))

    if breakdown:
        att_data = [
            ['Attendance Summary', '', '', ''],
            ['Total Working Days', str(breakdown.total_working_days), 'Days Present', str(breakdown.days_present)],
            ['Days Absent', str(breakdown.days_absent), 'Half Days', str(breakdown.days_half_day)],
            ['Days Late', str(breakdown.days_late), 'Holidays', str(breakdown.days_holiday)],
            ['Approved Leaves', str(breakdown.days_approved_leave), 'Attendance %', f'{breakdown.attendance_percentage}%'],
        ]
        att_table = Table(att_data, colWidths=[120, 80, 120, 80])
        att_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#36b9cc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('SPAN', (0, 0), (-1, 0)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f0f2f7')),
            ('BACKGROUND', (2, 1), (2, -1), colors.HexColor('#f0f2f7')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(att_table)
        elements.append(Spacer(1, 15))

    salary_data = [
        ['Earnings', 'Amount (Rs.)', 'Deductions', 'Amount (Rs.)'],
        ['Basic Salary', f'{payroll.basic_salary:,.2f}', 'Deductions', f'{payroll.deductions:,.2f}'],
        ['Allowances', f'{payroll.allowances:,.2f}', 'Tax', f'{payroll.tax:,.2f}'],
        ['', '', 'Total Deductions', f'{payroll.deductions + payroll.tax:,.2f}'],
        ['Total Earnings', f'{payroll.basic_salary + payroll.allowances:,.2f}', '', ''],
    ]

    salary_table = Table(salary_data, colWidths=[120, 100, 120, 100])
    salary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1cc88a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (2, 0), (3, 0), colors.HexColor('#e74a3b')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, -1), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, -1), (3, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (1, -1), colors.HexColor('#d4edda')),
        ('BACKGROUND', (2, -1), (3, -1), colors.HexColor('#f8d7da')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(salary_table)
    elements.append(Spacer(1, 20))

    net_style = ParagraphStyle('Net', parent=styles['Heading2'], alignment=1, textColor=colors.HexColor('#4e73df'))
    elements.append(Paragraph(f"NET SALARY: Rs. {payroll.net_salary:,.2f}", net_style))
    elements.append(Spacer(1, 30))

    elements.append(Paragraph("This is a computer-generated salary slip.", styles['Normal']))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d %b %Y %H:%M')}", styles['Normal']))

    doc.build(elements)
    return response


@login_required
@permission_required('manage_payroll')
def auto_generate_payroll(request):
    if request.method == 'POST':
        month = int(request.POST.get('month', datetime.now().month))
        year = int(request.POST.get('year', datetime.now().year))

        policy = get_active_policy()
        employees = Employee.objects.filter(status='active')

        department_id = request.POST.get('department', '').strip()
        employee_id = request.POST.get('employee', '').strip()
        staff = request.POST.get('staff', 'all').strip()

        if department_id:
            employees = employees.filter(department_id=department_id)
        if employee_id:
            employees = employees.filter(employee_id=employee_id)
        if staff == 'management':
            employees = employees.filter(managers_q())

        created_count = 0
        updated_count = 0
        errors = []

        for employee in employees:
            try:
                result = calculate_auto_payroll(employee, month, year, policy)

                payroll, created = Payroll.objects.update_or_create(
                    employee=employee,
                    month=month,
                    year=year,
                    defaults={
                        'basic_salary': result['basic_salary'],
                        'allowances': result['allowances'],
                        'deductions': result['deductions'],
                        'tax': result['tax'],
                        'net_salary': result['net_salary'],
                        'status': 'draft',
                        'generated_type': 'auto',
                        'notes': f"Auto-generated | Attendance: {result['breakdown']['attendance_percentage']}%",
                    }
                )

                PayrollBreakdown.objects.update_or_create(
                    payroll=payroll,
                    defaults=result['breakdown']
                )

                for issue in result.get('boutique_items', []):
                    issue.is_deducted = True
                    issue.deducted_in_payroll = payroll
                    issue.save()

                for loan in result.get('active_loans', []):
                    if loan.remaining_amount > 0:
                        deduction = min(loan.monthly_deduction, loan.remaining_amount)
                        loan.total_deducted += deduction
                        loan.remaining_amount -= deduction
                        if loan.remaining_amount <= 0:
                            loan.is_active = False
                        loan.save()

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                errors.append(f"{employee.employee_id}: {str(e)}")

        if created_count > 0:
            messages.success(request, f'Created {created_count} new payroll records.')
        if updated_count > 0:
            messages.info(request, f'Updated {updated_count} existing payroll records.')
        if created_count == 0 and updated_count == 0:
            messages.warning(request, 'No payroll records were created. No matching employees found for the selected filters.')
        if errors:
            for error in errors:
                messages.warning(request, error)

        return redirect('payroll_list')

    current_month = datetime.now().month
    current_year = datetime.now().year
    departments = Department.objects.all().order_by('name')
    employees = Employee.objects.filter(status='active').order_by('employee_id')
    return render(request, 'payroll/auto_generate.html', {
        'current_month': current_month,
        'current_year': current_year,
        'departments': departments,
        'payroll_employees': employees,
    })


@login_required
@permission_required('view_reports')
def policy_list(request):
    policies = PayrollPolicy.objects.all()
    return render(request, 'payroll/policy_list.html', {'policies': policies})


@login_required
@permission_required('manage_payroll')
def policy_create(request):
    if request.method == 'POST':
        form = PayrollPolicyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Policy created successfully.')
            return redirect('policy_list')
    else:
        form = PayrollPolicyForm()
    return render(request, 'payroll/policy_form.html', {'form': form, 'title': 'Create Policy'})


@login_required
@permission_required('manage_payroll')
def policy_update(request, pk):
    policy = get_object_or_404(PayrollPolicy, pk=pk)
    if request.method == 'POST':
        form = PayrollPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, 'Policy updated successfully.')
            return redirect('policy_list')
    else:
        form = PayrollPolicyForm(instance=policy)
    return render(request, 'payroll/policy_form.html', {'form': form, 'title': 'Edit Policy'})


@login_required
@permission_required('manage_payroll')
def policy_activate(request, pk):
    policy = get_object_or_404(PayrollPolicy, pk=pk)
    PayrollPolicy.objects.update(is_active=False)
    policy.is_active = True
    policy.save()
    messages.success(request, f'Policy "{policy.name}" activated.')
    return redirect('policy_list')


@login_required
@permission_required('manage_boutique')
def boutique_product_list(request):
    products = BoutiqueProduct.objects.all()
    paginator = Paginator(products, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'payroll/boutique_product_list.html', {
        'products': page_obj,
    })


@login_required
@permission_required('manage_boutique')
def boutique_product_create(request):
    if request.method == 'POST':
        form = BoutiqueProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product added successfully.')
            return redirect('boutique_product_list')
    else:
        form = BoutiqueProductForm()
    return render(request, 'payroll/boutique_product_form.html', {'form': form, 'title': 'Add Product'})


@login_required
@permission_required('manage_boutique')
def boutique_product_edit(request, pk):
    product = get_object_or_404(BoutiqueProduct, pk=pk)
    if request.method == 'POST':
        form = BoutiqueProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully.')
            return redirect('boutique_product_list')
    else:
        form = BoutiqueProductForm(instance=product)
    return render(request, 'payroll/boutique_product_form.html', {'form': form, 'title': 'Edit Product'})


@login_required
@permission_required('manage_boutique')
def boutique_product_delete(request, pk):
    product = get_object_or_404(BoutiqueProduct, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted successfully.')
        return redirect('boutique_product_list')
    return render(request, 'payroll/boutique_confirm_delete.html', {'product': product})


@login_required
@permission_required('manage_boutique')
def boutique_issue_list(request):
    issues = BoutiqueIssue.objects.select_related('employee', 'product').all()
    paginator = Paginator(issues, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    total_pending = issues.filter(is_deducted=False).aggregate(total=Sum('total_price'))['total'] or 0
    total_deducted = issues.filter(is_deducted=True).aggregate(total=Sum('total_price'))['total'] or 0
    return render(request, 'payroll/boutique_issue_list.html', {
        'issues': page_obj,
        'total_pending': total_pending,
        'total_deducted': total_deducted,
    })


@login_required
@permission_required('manage_boutique')
def boutique_issue_create(request):
    if request.method == 'POST':
        form = BoutiqueIssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.total_price = issue.product.price * issue.quantity
            issue.save()
            product = issue.product
            product.stock -= issue.quantity
            product.save()
            messages.success(request, f'{issue.product.name} issued to {issue.employee.first_name}. Will be deducted from salary.')
            return redirect('boutique_issue_list')
    else:
        form = BoutiqueIssueForm()
    return render(request, 'payroll/boutique_issue_form.html', {'form': form})


@login_required
@permission_required('manage_boutique')
def loan_list(request):
    loans = BudgetLoan.objects.select_related('employee').all()
    paginator = Paginator(loans, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    total_loan = loans.filter(is_active=True).aggregate(total=Sum('remaining_amount'))['total'] or 0
    total_deducted = loans.aggregate(total=Sum('total_deducted'))['total'] or 0
    return render(request, 'payroll/loan_list.html', {
        'loans': page_obj,
        'total_loan': total_loan,
        'total_deducted': total_deducted,
    })


@login_required
@permission_required('manage_boutique')
def loan_create(request):
    if request.method == 'POST':
        form = BudgetLoanForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Budget loan added successfully.')
            return redirect('loan_list')
    else:
        form = BudgetLoanForm()
    return render(request, 'payroll/loan_form.html', {'form': form})


@login_required
@permission_required('view_reports')
def department_salary(request):
    departments = Department.objects.all()
    dept_data = []
    for dept in departments:
        employees = Employee.objects.filter(department=dept, status='active')
        total_salary = employees.aggregate(total=Sum('salary'))['total'] or 0
        count = employees.count()
        avg_salary = total_salary / count if count > 0 else 0
        dept_data.append({
            'department': dept,
            'employee_count': count,
            'total_salary': total_salary,
            'avg_salary': avg_salary.quantize(Decimal('0.01')) if count > 0 else 0,
            'employees': employees,
        })
    grand_total = sum(d['total_salary'] for d in dept_data)
    total_employees = sum(d['employee_count'] for d in dept_data)
    return render(request, 'payroll/department_salary.html', {
        'dept_data': dept_data,
        'grand_total': grand_total,
        'total_employees': total_employees,
    })
