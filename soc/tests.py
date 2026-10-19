from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from employees.audit import log_audit
from employees.models import AuditLog, Employee
from soc.management.commands.run_soc_rules import seed_rules

from .engine import evaluate_event, open_alert, run_scan
from .models import Alert, DetectionRule, Incident, IncidentNote


def make_employee(username='EMP901', **kwargs):
    user = User.objects.create_user(username=username, password='x12345')
    defaults = {
        'employee_id': username, 'first_name': 'Test', 'last_name': 'User',
        'email': f'{username}@example.com', 'status': 'active',
        'is_authorized': True, 'role': 'employee',
        'date_of_joining': date(2024, 1, 1), 'salary': 50000,
    }
    defaults.update(kwargs)
    emp = Employee.objects.create(user=user, **defaults)
    return emp


class RuleSeedingTests(TestCase):
    def test_seed_rules_is_idempotent(self):
        seed_rules()
        first = DetectionRule.objects.count()
        seed_rules()
        self.assertEqual(DetectionRule.objects.count(), first)
        self.assertEqual(first, 9)


class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_rules()

    def _failed_logins(self, employee, n, ip='10.0.0.1'):
        for i in range(n):
            log_audit(
                user=employee.user, action='login_failed',
                model_name='Employee', object_id=employee.employee_id,
                description=f'Failed login for {employee.employee_id}',
                severity='low', outcome='failure', category='auth',
            )
        AuditLog.objects.filter(action='login_failed').update(ip_address=ip)

    def test_brute_force_fires_at_threshold(self):
        emp = make_employee()
        self._failed_logins(emp, 4)
        self.assertEqual(Alert.objects.filter(rule__key='brute_force').count(), 0)
        self._failed_logins(emp, 1)
        alerts = Alert.objects.filter(rule__key='brute_force')
        self.assertEqual(alerts.count(), 1)
        alert = alerts.get()
        self.assertEqual(alert.severity, 'critical')
        self.assertEqual(alert.subject_username, emp.user.username)
        self.assertEqual(alert.count, 1)

    def test_brute_force_deduplicates(self):
        emp = make_employee()
        self._failed_logins(emp, 5)
        self._failed_logins(emp, 3)
        alert = Alert.objects.get(rule__key='brute_force')
        self.assertEqual(alert.count, 4)
        self.assertEqual(Alert.objects.filter(rule__key='brute_force').count(), 1)

    def test_lockout_opens_high_alert(self):
        emp = make_employee()
        log_audit(
            user=emp.user, action='lockout', model_name='Employee',
            object_id=emp.employee_id, description='Account locked',
            severity='high', outcome='failure', category='auth',
        )
        alert = Alert.objects.get(rule__key='account_lockout')
        self.assertEqual(alert.severity, 'high')
        self.assertEqual(alert.subject_username, emp.employee_id)

    def test_locked_attempt_detected(self):
        emp = make_employee()
        log_audit(
            user=emp.user, action='login_failed', model_name='Employee',
            object_id=emp.employee_id,
            description='Login attempt while account is locked (EMP901)',
            severity='medium', outcome='failure', category='auth',
        )
        self.assertTrue(Alert.objects.filter(rule__key='locked_attempt').exists())

    def test_mass_export_detected(self):
        emp = make_employee()
        for i in range(10):
            log_audit(
                user=emp.user, action='export', model_name='Employee',
                object_id='Employee', description='Exported 5 Employee records',
                severity='low', category='data',
            )
        self.assertTrue(Alert.objects.filter(rule__key='mass_export').exists())

    def test_ip_switch_detected(self):
        emp = make_employee()
        log_audit(user=emp.user, action='login', model_name='User',
                  object_id=emp.user.username, description='User logged in',
                  category='auth', outcome='success')
        log_audit(user=emp.user, action='login', model_name='User',
                  object_id=emp.user.username, description='User logged in',
                  category='auth', outcome='success')
        AuditLog.objects.filter(action='login').update(ip_address=None)
        ips = ['1.1.1.1', '2.2.2.2']
        for event, ip in zip(AuditLog.objects.filter(action='login'), ips):
            AuditLog.objects.filter(pk=event.pk).update(ip_address=ip)
        evaluate_event(AuditLog.objects.filter(action='login').last())
        self.assertTrue(Alert.objects.filter(rule__key='ip_switch').exists())

    def test_disabled_rule_does_not_fire(self):
        emp = make_employee()
        DetectionRule.objects.filter(key='brute_force').update(enabled=False)
        self._failed_logins(emp, 6)
        self.assertFalse(Alert.objects.filter(rule__key='brute_force').exists())

    def test_run_scan_covers_recent_events(self):
        emp = make_employee()
        self._failed_logins(emp, 5)
        Alert.objects.all().delete()
        run_scan(hours=24)
        self.assertTrue(Alert.objects.filter(rule__key='brute_force').exists())


class PlaybookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_rules()

    @override_settings(SOC_AUTO_RESPONSE=True)
    def test_auto_lock_and_session_revoke(self):
        emp = make_employee()
        rule = DetectionRule.objects.get(key='brute_force')
        alert = open_alert(
            rule, 'fp-playbook-test', 'Brute force on EMP901',
            '5 failed logins', subject_username=emp.user.username)
        emp.refresh_from_db()
        self.assertTrue(emp.is_login_locked)
        self.assertEqual(alert.actions.filter(action='lock_account').count(), 1)
        self.assertEqual(alert.actions.filter(action='revoke_sessions').count(), 1)
        self.assertEqual(alert.actions.filter(action='open_ticket').count(), 1)
        self.assertTrue(AuditLog.objects.filter(
            action='lockout', description__icontains='SOC auto-response').exists())

    @override_settings(SOC_AUTO_RESPONSE=False)
    def test_playbooks_disabled(self):
        emp = make_employee()
        rule = DetectionRule.objects.get(key='brute_force')
        alert = open_alert(
            rule, 'fp-disabled', 'Brute force', 'x',
            subject_username=emp.user.username)
        emp.refresh_from_db()
        self.assertFalse(emp.is_login_locked)
        self.assertEqual(alert.actions.count(), 0)


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_rules()
        cls.employee = make_employee('EMPPERM')
        cls.it_staff = make_employee(
            'IT001', support_team='networks', role='employee')
        cls.admin = User.objects.create_superuser('sochost', password='x12345')

    def test_employee_cannot_open_soc(self):
        self.client.force_login(self.employee.user)
        resp = self.client.get(reverse('soc_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_it_staff_can_open_soc(self):
        self.client.force_login(self.it_staff.user)
        resp = self.client.get(reverse('soc_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_admin_sees_rules_page(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('soc_rule_list'))
        self.assertEqual(resp.status_code, 200)

    def test_all_soc_pages_render(self):
        rule = DetectionRule.objects.get(key='privilege_change')
        alert = open_alert(rule, 'fp-render', 'Render check', 'detail',
                           subject_username='X')
        incident = Incident.objects.create(title='Render incident', severity='high')
        alert.incident = incident
        alert.save()
        self.client.force_login(self.it_staff.user)
        for name, args in [
            ('soc_dashboard', []), ('soc_event_list', []),
            ('soc_alert_list', []), ('soc_alert_detail', [alert.pk]),
            ('soc_incident_list', []), ('soc_incident_detail', [incident.pk]),
        ]:
            resp = self.client.get(reverse(name, args=args))
            self.assertEqual(resp.status_code, 200, f'{name} failed: {resp.status_code}')
        self.client.force_login(self.admin)
        for name in ('soc_rule_list',):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, f'{name} failed: {resp.status_code}')

    def test_employee_cannot_toggle_rule(self):
        rule = DetectionRule.objects.get(key='privilege_change')
        before = rule.enabled
        self.client.force_login(self.employee.user)
        resp = self.client.post(reverse('soc_rule_toggle', args=[rule.pk]),
                                {'field': 'enabled'})
        self.assertEqual(resp.status_code, 302)
        rule.refresh_from_db()
        self.assertEqual(rule.enabled, before)


class IncidentFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_rules()
        cls.it_staff = make_employee('IT002', support_team='networks')
        cls.alert = None

    def _make_alert(self):
        rule = DetectionRule.objects.get(key='privilege_change')
        return open_alert(rule, 'fp-incident', 'Privilege change: authorize X',
                          'detail', subject_username='X')

    def test_escalate_creates_incident(self):
        alert = self._make_alert()
        self.client.force_login(self.it_staff.user)
        resp = self.client.post(reverse('soc_alert_action', args=[alert.pk]),
                                {'action': 'escalate'})
        self.assertEqual(resp.status_code, 302)
        alert.refresh_from_db()
        self.assertIsNotNone(alert.incident)
        self.assertEqual(alert.status, 'acknowledged')
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(IncidentNote.objects.filter(
            incident=alert.incident).count(), 1)

    def test_incident_status_workflow(self):
        alert = self._make_alert()
        incident = Incident.objects.create(title='Test', severity='high')
        alert.incident = incident
        alert.save()
        self.client.force_login(self.it_staff.user)
        resp = self.client.post(reverse('soc_incident_update', args=[incident.pk]),
                                {'status': 'contained', 'note': 'IP blocked'})
        self.assertEqual(resp.status_code, 302)
        incident.refresh_from_db()
        self.assertEqual(incident.status, 'contained')
        self.assertEqual(incident.notes.filter(kind='comment').count(), 1)


class CronEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_rules()

    def test_requires_secret(self):
        resp = self.client.get(reverse('soc_cron_scan'))
        self.assertEqual(resp.status_code, 403)

    @override_settings(SOC_CRON_SECRET='s3cret-value')
    def test_accepts_bearer_token(self):
        resp = self.client.get(reverse('soc_cron_scan'),
                               HTTP_AUTHORIZATION='Bearer s3cret-value')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    @override_settings(SOC_CRON_SECRET='s3cret-value')
    def test_rejects_wrong_token(self):
        resp = self.client.get(reverse('soc_cron_scan'),
                               HTTP_AUTHORIZATION='Bearer wrong')
        self.assertEqual(resp.status_code, 403)


class LoginAuditTests(TestCase):
    def test_failed_login_writes_audit_event(self):
        emp = make_employee('EMPLOGIN')
        self.client.post(reverse('login'), {
            'username': 'EMPLOGIN', 'password': 'wrong-password'})
        event = AuditLog.objects.filter(action='login_failed').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.outcome, 'failure')
        self.assertEqual(event.category, 'auth')

    def test_successful_login_writes_audit_event(self):
        emp = make_employee('EMPLOGIN2')
        emp.user.set_password('goodpass123')
        emp.user.save()
        self.client.post(reverse('login'), {
            'username': 'EMPLOGIN2', 'password': 'goodpass123'})
        self.assertTrue(AuditLog.objects.filter(
            action='login', object_id='EMPLOGIN2').exists())

    def test_export_writes_audit_event(self):
        from employees.views_reports import _audit_export
        from django.test import RequestFactory
        emp = make_employee('EMPXPORT')
        self.client.force_login(emp.user)
        request = RequestFactory().get('/x')
        request.user = emp.user
        _audit_export(request, 'Employee', 42)
        event = AuditLog.objects.filter(action='export').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.category, 'data')
