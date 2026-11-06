from datetime import timedelta

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from hr_payroll.middleware import IdleSessionTimeoutMiddleware


@override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
class IdleSessionTimeoutMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request_with_session(self, user):
        request = self.factory.get('/dashboard/')
        SessionMiddleware(lambda request: None).process_request(request)
        request.user = user
        return request

    @override_settings(SESSION_IDLE_TIMEOUT=120)
    def test_recent_activity_keeps_authenticated_session(self):
        request = self.request_with_session(User(username='active-user'))
        request.session[IdleSessionTimeoutMiddleware.SESSION_KEY] = timezone.now().timestamp() - 60
        response = IdleSessionTimeoutMiddleware(lambda request: HttpResponse('ok'))(request)

        self.assertEqual(response.content, b'ok')
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')
        self.assertIn(IdleSessionTimeoutMiddleware.SESSION_KEY, request.session)

    @override_settings(SESSION_IDLE_TIMEOUT=120)
    def test_idle_session_is_logged_out_and_redirected(self):
        request = self.request_with_session(User(username='idle-user'))
        request.session[IdleSessionTimeoutMiddleware.SESSION_KEY] = (
            timezone.now() - timedelta(seconds=121)
        ).timestamp()
        response = IdleSessionTimeoutMiddleware(lambda request: HttpResponse('ok'))(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')
        self.assertIsInstance(request.user, AnonymousUser)

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from employees.models import Department, Employee
from employees.permissions import can_manage_employee_records
from employees.views import employee_scope, save_employee_with_unique_id


class EmployeeTestCase(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Operations')

    def _employee(self, employee_id='EMP001', email='ada@example.com', **kwargs):
        defaults = {
            'first_name': 'Ada', 'last_name': 'Lovelace',
            'department': self.department, 'date_of_joining': date(2024, 1, 1),
            'salary': Decimal('3000.00'), 'status': 'active',
        }
        defaults.update(kwargs)
        return Employee.objects.create(
            employee_id=employee_id, email=email, **defaults)


class MiddlewareTests(EmployeeTestCase):
    def test_unauthorized_employee_is_logged_out(self):
        user = User.objects.create_user(username='blocked', password='pass12345')
        self._employee(user=user, is_authorized=False)
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', client.session)

    def test_inactive_employee_is_logged_out(self):
        user = User.objects.create_user(username='inactive', password='pass12345')
        self._employee(user=user, is_authorized=True, status='inactive')
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_must_change_password_redirects_to_change_password(self):
        user = User.objects.create_user(username='newhire', password='pass12345')
        self._employee(user=user, is_authorized=True, must_change_password=True)
        client = Client()
        client.force_login(user)

        response = client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('change_password'))

    def test_must_change_password_allows_change_password_page(self):
        user = User.objects.create_user(username='newhire', password='pass12345')
        self._employee(user=user, is_authorized=True, must_change_password=True)
        client = Client()
        client.force_login(user)

        response = client.get(reverse('change_password'))

        self.assertEqual(response.status_code, 200)


class EmployeeIdTests(EmployeeTestCase):
    def test_id_collision_is_retried(self):
        self._employee(employee_id='EMP001')
        employee = Employee(
            first_name='Grace', last_name='Hopper', email='grace@example.com',
            department=self.department, date_of_joining=date(2024, 1, 1),
            salary=Decimal('4000.00'), status='active',
        )

        with patch('employees.views.generate_employee_id',
                   side_effect=['EMP001', 'EMP002']):
            save_employee_with_unique_id(employee)

        self.assertEqual(employee.employee_id, 'EMP002')
        self.assertTrue(Employee.objects.filter(employee_id='EMP002').exists())


class EmployeeAccessTests(EmployeeTestCase):
    def setUp(self):
        super().setUp()
        self.hr = Department.objects.create(name='Human Resources')
        self.management = Department.objects.create(name='Management')
        self.sales = Department.objects.create(name='Sales')
        self.other = self._employee(
            employee_id='EMP900', email='other@example.com')

    def _account(self, employee_id, email, department, **kwargs):
        user = User.objects.create_user(
            username=employee_id, email=email, password='pass12345')
        defaults = {
            'first_name': employee_id, 'last_name': 'User',
            'department': department, 'date_of_joining': date(2024, 1, 1),
            'salary': Decimal('3000.00'), 'status': 'active',
            'user': user, 'is_authorized': True,
        }
        defaults.update(kwargs)
        return self._employee(
            employee_id=employee_id, email=email, **defaults)

    def _client_for(self, employee):
        client = Client()
        client.force_login(employee.user)
        return client

    def test_department_manager_cannot_view_employee_directory(self):
        manager = self._account(
            'MGR001', 'sales.manager@example.com', self.sales,
            designation='Sales Manager', role='employee')
        client = self._client_for(manager)

        response = client.get(reverse('employee_list'))

        self.assertRedirects(response, reverse('dashboard'))
        self.assertNotIn('view_employees', manager.permissions)
        self.assertNotIn('manage_employees', manager.permissions)
        visible, _, _ = employee_scope(manager.user)
        self.assertEqual(visible.count(), 1)

    def test_department_manager_cannot_edit_another_employee(self):
        manager = self._account(
            'MGR002', 'sales.manager2@example.com', self.sales,
            designation='Sales Manager', role='employee')
        client = self._client_for(manager)

        response = client.get(reverse('employee_update', args=[self.other.pk]))

        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(can_manage_employee_records(manager.user))

    def test_hr_department_can_view_and_manage_all_employees(self):
        hr_user = self._account(
            'HR001', 'hr.user@example.com', self.hr,
            designation='HR Assistant', role='hr')
        client = self._client_for(hr_user)

        response = client.get(reverse('employee_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.other.employee_id)
        self.assertIn('view_employees', hr_user.permissions)
        self.assertIn('manage_employees', hr_user.permissions)
        self.assertTrue(can_manage_employee_records(hr_user.user))

    def test_management_department_can_view_and_manage_all_employees(self):
        mgmt_user = self._account(
            'MGMT001', 'management.user@example.com', self.management,
            designation='General Manager', role='manager')
        client = self._client_for(mgmt_user)

        response = client.get(reverse('employee_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.other.employee_id)
        self.assertIn('view_employees', mgmt_user.permissions)
        self.assertTrue(can_manage_employee_records(mgmt_user.user))

    def test_employee_record_permissions_are_granted_by_department_only(self):
        manager = self._account(
            'MGR003', 'sales.manager3@example.com', self.sales,
            designation='Sales Manager', role='employee')

        for perm in ('view_employees', 'manage_employees', 'bulk_import',
                     'approve_access', 'manage_faces'):
            self.assertNotIn(perm, manager.permissions)
