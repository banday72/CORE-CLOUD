from datetime import date
from decimal import Decimal

from django.test import TestCase

from employees.models import Department, Employee
from leaves.forms import LeaveForm
from leaves.models import Leave, LeaveBalance, LeaveType, count_business_days


class LeaveTestCase(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Operations')
        self.employee = Employee.objects.create(
            employee_id='EMP001', first_name='Ada', last_name='Lovelace',
            email='ada@example.com', department=self.department,
            date_of_joining=date(2024, 1, 1), salary=Decimal('3000.00'),
            status='active', is_authorized=True,
        )
        self.leave_type = LeaveType.objects.create(name='Annual', days_per_year=20)


class BusinessDayTests(LeaveTestCase):
    def test_weekend_is_excluded(self):
        self.assertEqual(count_business_days(date(2026, 1, 2), date(2026, 1, 5)), 2)

    def test_reversed_range_has_no_days(self):
        self.assertEqual(count_business_days(date(2026, 1, 5), date(2026, 1, 2)), 0)

    def test_leave_total_days_counts_weekdays(self):
        leave = Leave.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 1, 2), end_date=date(2026, 1, 5),
            reason='Trip', status='approved',
        )
        self.assertEqual(leave.total_days, 2)


class LeaveBalanceTests(LeaveTestCase):
    def test_cross_year_leave_is_split_between_balances(self):
        Leave.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2025, 12, 30), end_date=date(2026, 1, 2),
            reason='Holiday', status='approved',
        )
        balance_2025 = LeaveBalance.objects.create(
            employee=self.employee, leave_type=self.leave_type, year=2025, allocated=10)
        balance_2026 = LeaveBalance.objects.create(
            employee=self.employee, leave_type=self.leave_type, year=2026, allocated=10)

        self.assertEqual(balance_2025.used, 2)
        self.assertEqual(balance_2026.used, 2)


class LeaveFormTests(LeaveTestCase):
    def _form(self, start, end, **overrides):
        data = {
            'employee': self.employee.pk,
            'leave_type': self.leave_type.pk,
            'start_date': start,
            'end_date': end,
            'reason': 'Family event',
        }
        data.update(overrides)
        return LeaveForm(data=data)

    def test_end_before_start_is_invalid(self):
        form = self._form(date(2026, 2, 6), date(2026, 2, 2))
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_weekend_only_range_is_invalid(self):
        form = self._form(date(2026, 1, 3), date(2026, 1, 4))
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_overlapping_pending_leave_is_invalid(self):
        Leave.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 2, 2), end_date=date(2026, 2, 4),
            reason='Existing', status='pending',
        )
        form = self._form(date(2026, 2, 4), date(2026, 2, 6))
        self.assertFalse(form.is_valid())
        self.assertIn('start_date', form.errors)

    def test_non_overlapping_leave_is_valid(self):
        Leave.objects.create(
            employee=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 2, 2), end_date=date(2026, 2, 4),
            reason='Existing', status='pending',
        )
        form = self._form(date(2026, 2, 5), date(2026, 2, 6))
        self.assertTrue(form.is_valid(), form.errors)
