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

# Create your tests here.
