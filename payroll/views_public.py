from django.shortcuts import render, get_object_or_404
from django.views.decorators.clickjacking import xframe_options_exempt
from .models import Payroll, PublicPayrollLink


@xframe_options_exempt
def public_salary_slip(request, employee_id, token):
    link = get_object_or_404(
        PublicPayrollLink,
        employee__employee_id=employee_id,
        token=token,
        is_active=True
    )
    employee = link.employee
    payrolls = Payroll.objects.filter(employee=employee).order_by('-year', '-month')[:12]

    return render(request, 'payroll/public_salary_slip.html', {
        'employee': employee,
        'payrolls': payrolls,
        'company_name': 'CoreCloud',
        'company_tagline': 'CoreCloud HR Payroll',
        'is_public': True,
    })
