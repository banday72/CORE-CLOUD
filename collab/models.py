"""Internal collaboration: Mail (Outlook-like), Chat (Teams-like) and Meetings.

Everything here is intentionally database-backed so it works on serverless
hosting (Vercel) where WebSockets are not available. Chat uses short polling.
Meetings embed a free Jitsi Meet room (no extra server needed).
"""

from django.db import models
from django.utils import timezone

import hashlib

from employees.models import Employee


class Conversation(models.Model):
    KIND_DIRECT = 'direct'
    KIND_GROUP = 'group'
    KIND_CHOICES = [
        (KIND_DIRECT, 'Direct'),
        (KIND_GROUP, 'Group'),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_DIRECT)
    title = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conversations_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f'{self.get_kind_display()} #{self.pk}'

    def display_title(self, me=None):
        if self.title:
            return self.title
        names = [
            m.employee.full_name
            for m in self.members.select_related('employee')
            if me is None or m.employee_id != me.pk
        ]
        if names:
            return ', '.join(names[:3]) + ('…' if len(names) > 3 else '')
        return 'Just you'

    @property
    def call_room(self):
        digest = hashlib.sha1(f'corecloud-chat-{self.pk}'.encode()).hexdigest()[:14]
        return f'CoreCloud-Chat-{digest}'


class ConversationMember(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='members')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='chat_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('conversation', 'employee')

    def __str__(self):
        return f'{self.employee} in {self.conversation}'


class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_messages',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender}: {self.body[:40]}'


class MailMessage(models.Model):
    """An internal mail (Outlook-like). One row per sent message."""

    sender = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mails_sent',
    )
    subject = models.CharField(max_length=300)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.subject


class MailRecipient(models.Model):
    mail = models.ForeignKey(MailMessage, on_delete=models.CASCADE, related_name='recipients')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='mails_received')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.mail.subject} → {self.employee}'


class Meeting(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    title = models.CharField(max_length=200)
    agenda = models.TextField(blank=True)
    organizer = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='meetings_organized',
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    room = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_at']

    def __str__(self):
        return self.title

    @property
    def join_url(self):
        return f'https://meet.jit.si/{self.room}' if self.room else ''

    @property
    def is_upcoming(self):
        return self.status == 'scheduled' and self.start_at >= timezone.now()


class MeetingAttendee(models.Model):
    STATUS_CHOICES = [
        ('invited', 'Invited'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='attendees')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='meeting_invites')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='invited')

    class Meta:
        unique_together = ('meeting', 'employee')

    def __str__(self):
        return f'{self.employee} @ {self.meeting}'
