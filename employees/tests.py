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
from employees.views import save_employee_with_unique_id


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
