from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from employees.models import Department, Employee

from .models import MailMessage, MailRecipient, MailSettings


class InternalMailTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Engineering')
        self.a = self._make_employee('EMP100', 'Alice', 'Adams', 'Engineer')
        self.b = self._make_employee('EMP101', 'Bob', 'Brown', 'Manager')
        self.c = self._make_employee('EMP102', 'Carol', 'Clark', 'Designer')
        self.client.force_login(self.a.user)

    def _make_employee(self, emp_id, first, last, designation):
        user = User.objects.create_user(username=emp_id, password='employee123')
        return Employee.objects.create(
            user=user, employee_id=emp_id, first_name=first, last_name=last,
            email=f'{emp_id.lower()}@example.com', department=self.dept,
            designation=designation, date_of_joining=date(2020, 1, 1),
            salary=Decimal('1000.00'), status='active',
        )

    def _mail_from_b_to_a(self):
        mail = MailMessage.objects.create(sender=self.b, subject='Project', body='line1\nline2')
        MailRecipient.objects.create(mail=mail, employee=self.a, kind=MailRecipient.KIND_TO)
        return mail

    def test_compose_provides_searchable_employee_data(self):
        resp = self.client.get(reverse('collab_mail_compose'))
        self.assertEqual(resp.status_code, 200)
        data = {e['id']: e for e in resp.context['employee_data']}
        self.assertEqual(data[self.b.pk]['designation'], 'Manager')
        self.assertEqual(data[self.b.pk]['name'], 'Bob Brown')

    def test_compose_sends_to_and_cc(self):
        resp = self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Hello',
            'body': 'Hi there',
            'recipients': [self.b.pk],
            'cc_recipients': [self.c.pk],
        })
        self.assertRedirects(resp, reverse('collab_mail_sent'))
        mail = MailMessage.objects.get()
        self.assertEqual(mail.sender, self.a)
        kinds = {r.employee_id: r.kind for r in mail.recipients.all()}
        self.assertEqual(kinds[self.b.pk], MailRecipient.KIND_TO)
        self.assertEqual(kinds[self.c.pk], MailRecipient.KIND_CC)

    def test_cc_is_not_duplicated_when_also_in_to(self):
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Hello', 'body': 'Body',
            'recipients': [self.b.pk], 'cc_recipients': [self.b.pk],
        })
        mail = MailMessage.objects.get()
        self.assertEqual(mail.recipients.count(), 1)
        self.assertEqual(mail.recipients.first().kind, MailRecipient.KIND_TO)

    def test_cannot_send_to_self_only(self):
        resp = self.client.post(reverse('collab_mail_compose'), {
            'subject': 'x', 'body': 'y', 'recipients': [self.a.pk],
        })
        self.assertEqual(MailMessage.objects.count(), 0)
        self.assertContains(resp, 'at least one recipient')

    def test_reply_redirects_with_mode(self):
        mail = self._mail_from_b_to_a()
        resp = self.client.get(reverse('collab_mail_reply', args=[mail.pk]))
        self.assertTrue(resp.url.startswith(reverse('collab_mail_compose')))
        self.assertIn(f'reply_to={mail.pk}', resp.url)
        self.assertIn('mode=reply', resp.url)

    def test_reply_prefills_sender_only(self):
        mail = self._mail_from_b_to_a()
        resp = self.client.get(
            reverse('collab_mail_compose'), {'reply_to': mail.pk, 'mode': 'reply'})
        self.assertEqual(resp.context['initial_to'], [self.b.pk])
        self.assertEqual(resp.context['initial_cc'], [])
        self.assertEqual(resp.context['initial_subject'], 'Re: Project')
        self.assertEqual(resp.context['initial_body'], '')
        self.assertEqual(resp.context['quote_mode'], 'reply')
        self.assertIn('line1', resp.context['quote_html'])

    def test_reply_prefills_quote_block_ui(self):
        mail = self._mail_from_b_to_a()
        resp = self.client.get(
            reverse('collab_mail_compose'), {'reply_to': mail.pk, 'mode': 'reply'})
        self.assertContains(resp, 'id="quoteWrap"')
        self.assertContains(resp, 'id="deleteQuote"')
        self.assertContains(resp, 'name="include_quote"')
        self.assertContains(resp, 'name="mail_type"')

    def test_forward_mode_prefills_forwarded_block(self):
        mail = self._mail_from_b_to_a()
        resp = self.client.get(
            reverse('collab_mail_compose'), {'reply_to': mail.pk, 'mode': 'forward'})
        self.assertEqual(resp.context['initial_to'], [])
        self.assertEqual(resp.context['initial_subject'], 'Fwd: Project')
        self.assertEqual(resp.context['quote_mode'], 'forward')
        self.assertIn('Forwarded message', resp.context['quote_html'])
        self.assertIn('line1', resp.context['quote_html'])

    def test_forward_url_route_redirects(self):
        mail = self._mail_from_b_to_a()
        resp = self.client.get(reverse('collab_mail_forward', args=[mail.pk]))
        self.assertIn(f'reply_to={mail.pk}', resp.url)
        self.assertIn('mode=forward', resp.url)

    def test_reply_all_includes_other_recipients(self):
        mail = MailMessage.objects.create(sender=self.b, subject='Project', body='body')
        MailRecipient.objects.create(mail=mail, employee=self.a, kind=MailRecipient.KIND_TO)
        MailRecipient.objects.create(mail=mail, employee=self.c, kind=MailRecipient.KIND_CC)
        resp = self.client.get(
            reverse('collab_mail_compose'), {'reply_to': mail.pk, 'mode': 'reply_all'})
        self.assertEqual(resp.context['initial_to'], [self.b.pk, self.c.pk])
        self.assertEqual(resp.context['initial_cc'], [])

    def test_reply_with_cc_puts_others_in_cc(self):
        mail = MailMessage.objects.create(sender=self.b, subject='Project', body='body')
        MailRecipient.objects.create(mail=mail, employee=self.a, kind=MailRecipient.KIND_TO)
        MailRecipient.objects.create(mail=mail, employee=self.c, kind=MailRecipient.KIND_CC)
        resp = self.client.get(
            reverse('collab_mail_compose'), {'reply_to': mail.pk, 'mode': 'cc'})
        self.assertEqual(resp.context['initial_to'], [self.b.pk])
        self.assertEqual(resp.context['initial_cc'], [self.c.pk])

    def test_reply_post_links_parent(self):
        mail = self._mail_from_b_to_a()
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Re: Project', 'body': 'thanks',
            'recipients': [self.b.pk], 'parent': mail.pk,
        })
        reply = MailMessage.objects.exclude(pk=mail.pk).get()
        self.assertEqual(reply.parent, mail)

    def test_reply_post_stores_quote_separately_from_typed_text(self):
        mail = self._mail_from_b_to_a()
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Re: Project', 'body': 'thanks',
            'recipients': [self.b.pk], 'parent': mail.pk,
            'include_quote': '1', 'quote_mode': 'reply',
        })
        reply = MailMessage.objects.exclude(pk=mail.pk).get()
        self.assertEqual(reply.body, 'thanks')
        self.assertIn('line1', reply.quoted)
        self.assertNotIn('line1', reply.body)

    def test_reply_post_without_deleted_quote_stores_no_quote(self):
        mail = self._mail_from_b_to_a()
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Re: Project', 'body': 'rewritten from scratch',
            'recipients': [self.b.pk], 'parent': mail.pk,
            'include_quote': '0', 'quote_mode': 'reply',
        })
        reply = MailMessage.objects.exclude(pk=mail.pk).get()
        self.assertEqual(reply.body, 'rewritten from scratch')
        self.assertEqual(reply.quoted, '')

    def test_html_mail_is_sanitized_before_save(self):
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Hello', 'mail_type': 'html',
            'body': '<p>Hi<script>alert(1)</script><b>there</b></p>',
            'recipients': [self.b.pk],
        })
        mail = MailMessage.objects.get()
        self.assertEqual(mail.mail_type, 'html')
        self.assertNotIn('<script', mail.body)
        self.assertIn('<b>there</b>', mail.body)

    def test_html_mail_rejects_blank_rich_content(self):
        resp = self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Hello', 'mail_type': 'html', 'body': '<p><br></p>',
            'recipients': [self.b.pk],
        })
        self.assertEqual(MailMessage.objects.count(), 0)
        self.assertContains(resp, 'at least one recipient')

    def test_signature_appended_when_enabled(self):
        prefs = MailSettings.get()
        prefs.use_signature = True
        prefs.signature = 'Best regards,\nHuman Resources'
        prefs.save()
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Hello', 'body': 'Hi there',
            'recipients': [self.b.pk],
        })
        mail = MailMessage.objects.get()
        self.assertTrue(mail.body.startswith('Hi there'))
        self.assertIn('Best regards,', mail.body)

    def test_settings_page_denied_for_regular_employee(self):
        resp = self.client.get(reverse('collab_mail_settings'))
        self.assertRedirects(resp, reverse('dashboard'))

    def test_settings_page_renders_for_hr_and_saves(self):
        hr = self._make_employee('EMP200', 'Hannah', 'Hussain', 'HR Manager')
        self.client.force_login(hr.user)
        resp = self.client.get(reverse('collab_mail_settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Default email type')

        resp = self.client.post(reverse('collab_mail_settings'), {
            'include_quote_in_reply': '1',
            'use_signature': '1',
            'signature': 'Best, HR',
            'default_mail_type': 'html',
            'forward_style': 'quote',
        })
        self.assertRedirects(resp, reverse('collab_mail_settings'))
        prefs = MailSettings.get()
        self.assertTrue(prefs.include_quote_in_reply)
        self.assertTrue(prefs.use_signature)
        self.assertEqual(prefs.signature, 'Best, HR')
        self.assertEqual(prefs.default_mail_type, 'html')
        self.assertEqual(prefs.forward_style, 'quote')

    def test_disabling_quote_in_settings_removes_reply_prefill(self):
        prefs = MailSettings.get()
        prefs.include_quote_in_reply = False
        prefs.save()
        mail = self._mail_from_b_to_a()
        resp = self.client.get(
            reverse('collab_mail_compose'), {'reply_to': mail.pk, 'mode': 'reply'})
        self.assertEqual(resp.context['quote_html'], '')
        self.assertEqual(resp.context['initial_body'], '')

    def test_settings_link_hidden_without_permission(self):
        mail = self._mail_from_b_to_a()
        rec = mail.recipients.get(employee=self.a)
        resp = self.client.get(reverse('collab_mail_detail', args=[rec.pk]))
        self.assertNotContains(resp, reverse('collab_mail_settings'))

    def test_detail_has_inline_reply(self):
        mail = self._mail_from_b_to_a()
        rec = mail.recipients.get(employee=self.a)
        resp = self.client.get(reverse('collab_mail_detail', args=[rec.pk]))
        self.assertContains(resp, 'Reply all')
        self.assertContains(resp, 'Forward')
        self.assertContains(resp, 'data-mode="reply"')
        self.assertContains(resp, 'id="replyCard"')
        variants = resp.context['reply_variants']
        self.assertEqual(variants['reply']['to'], [self.b.pk])
        self.assertEqual(variants['reply']['subject'], 'Re: Project')
        self.assertIn('On ', variants['reply']['quote'])
        self.assertNotIn('body', variants['reply'])

    def test_detail_reply_all_and_forward_variants(self):
        mail = MailMessage.objects.create(sender=self.b, subject='Project', body='body')
        MailRecipient.objects.create(mail=mail, employee=self.a, kind=MailRecipient.KIND_TO)
        MailRecipient.objects.create(mail=mail, employee=self.c, kind=MailRecipient.KIND_CC)
        rec = mail.recipients.get(employee=self.a)
        resp = self.client.get(reverse('collab_mail_detail', args=[rec.pk]))
        variants = resp.context['reply_variants']
        self.assertEqual(variants['reply_all']['to'], [self.b.pk])
        self.assertEqual(variants['reply_all']['cc'], [self.c.pk])
        self.assertEqual(variants['forward']['to'], [])
        self.assertEqual(variants['forward']['subject'], 'Fwd: Project')
        self.assertEqual(variants['forward']['mode'], 'forward')
        self.assertIn('Forwarded message', variants['forward']['quote'])

    def test_sent_list_shows_cc(self):
        self.client.post(reverse('collab_mail_compose'), {
            'subject': 'Hello', 'body': 'Body',
            'recipients': [self.b.pk], 'cc_recipients': [self.c.pk],
        })
        resp = self.client.get(reverse('collab_mail_sent'))
        self.assertContains(resp, 'Cc:')
        self.assertContains(resp, 'Carol Clark')
