from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from attendance.models import Attendance
from employees.models import Department, Employee
from payroll.models import BudgetLoan, LoanDeduction, Payroll, PayrollPolicy
from payroll.views import _generate_one_payroll, calculate_auto_payroll


class PayrollTestCase(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Operations')
        self.user = User.objects.create_user(username='worker', password='pass12345')
        self.employee = Employee.objects.create(
            employee_id='EMP001', first_name='Ada', last_name='Lovelace',
            email='ada@example.com', department=self.department,
            date_of_joining=date(2024, 1, 1), salary=Decimal('3000.00'),
            role='employee', status='active', is_authorized=True, user=self.user,
        )
        self.policy = PayrollPolicy.objects.create(
            name='Test Policy', working_days_per_month=20,
            use_per_day_salary_for_absent=True, half_day_deduction_percent=50,
            late_allowed_per_month=1, late_deduction_amount=Decimal('100.00'),
            tax_rate_percent=10, performance_bonus_enabled=False,
            medical_allowance=0, transport_allowance=0, house_allowance_percent=0,
            is_active=True,
        )


class CalculatePayrollTests(PayrollTestCase):
    def test_late_day_is_not_double_deducted(self):
        for day in range(1, 19):
            Attendance.objects.create(
                employee=self.employee, date=date(2026, 1, day), status='present')
        for day in (19, 20):
            Attendance.objects.create(
                employee=self.employee, date=date(2026, 1, day), status='late')

        result = calculate_auto_payroll(self.employee, 1, 2026, self.policy)

        self.assertEqual(result['breakdown']['days_absent'], 0)
        self.assertEqual(result['basic_salary'], Decimal('3000.00'))
        self.assertEqual(result['deductions'], Decimal('100.00'))
        self.assertEqual(result['tax'], Decimal('290.00'))
        self.assertEqual(result['net_salary'], Decimal('2610.00'))

    def test_deductions_field_excludes_tax(self):
        for day in range(1, 21):
            Attendance.objects.create(
                employee=self.employee, date=date(2026, 1, day), status='present')

        result = calculate_auto_payroll(self.employee, 1, 2026, self.policy)

        self.assertEqual(result['basic_salary'], Decimal('3000.00'))
        self.assertEqual(result['deductions'], Decimal('0.00'))
        self.assertEqual(result['tax'], Decimal('300.00'))
        self.assertEqual(result['net_salary'], Decimal('2700.00'))


class PayrollGenerationTests(PayrollTestCase):
    def test_regeneration_does_not_double_charge_loan(self):
        loan = BudgetLoan.objects.create(
            employee=self.employee, loan_amount=Decimal('1000.00'),
            monthly_deduction=Decimal('300.00'), reason='Advance',
            start_date=date(2026, 1, 1), is_active=True,
        )
        loan.refresh_from_db()
        self.assertEqual(loan.remaining_amount, Decimal('1000.00'))

        _generate_one_payroll(self.employee, 1, 2026, self.policy)
        loan.refresh_from_db()
        self.assertEqual(loan.remaining_amount, Decimal('700.00'))
        self.assertEqual(loan.total_deducted, Decimal('300.00'))

        _generate_one_payroll(self.employee, 1, 2026, self.policy)
        loan.refresh_from_db()
        self.assertEqual(loan.remaining_amount, Decimal('700.00'))
        self.assertEqual(loan.total_deducted, Decimal('300.00'))
        self.assertEqual(
            LoanDeduction.objects.filter(loan=loan).count(), 1)
        self.assertEqual(
            LoanDeduction.objects.get(loan=loan).amount, Decimal('300.00'))


class PayslipAccessTests(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.payroll = Payroll.objects.create(
            employee=self.employee, month=1, year=2026,
            basic_salary=Decimal('3000.00'), allowances=Decimal('0.00'),
            deductions=Decimal('0.00'), tax=Decimal('300.00'),
            net_salary=Decimal('2700.00'), status='processed',
        )
        other_user = User.objects.create_user(username='other', password='pass12345')
        self.other = Employee.objects.create(
            employee_id='EMP002', first_name='Grace', last_name='Hopper',
            email='grace@example.com', department=self.department,
            date_of_joining=date(2024, 1, 1), salary=Decimal('4000.00'),
            role='employee', status='active', is_authorized=True, user=other_user,
        )
        self.other_payroll = Payroll.objects.create(
            employee=self.other, month=1, year=2026,
            basic_salary=Decimal('4000.00'), allowances=Decimal('0.00'),
            deductions=Decimal('0.00'), tax=Decimal('400.00'),
            net_salary=Decimal('3600.00'), status='processed',
        )

    def test_employee_can_download_own_payslip(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('my_payslip_pdf', args=[2026, 1]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_employee_cannot_download_another_employees_payslip(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('salary_slip_pdf', args=[self.other_payroll.pk]))
        self.assertEqual(response.status_code, 403)

    def test_employee_cannot_fetch_another_employees_payslip_by_month(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('my_payslip_pdf', args=[2026, 2]))
        self.assertEqual(response.status_code, 404)
