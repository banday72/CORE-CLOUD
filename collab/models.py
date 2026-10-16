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


MAIL_TYPE_PLAIN = 'plain'
MAIL_TYPE_HTML = 'html'
MAIL_TYPE_CHOICES = [
    (MAIL_TYPE_PLAIN, 'Plain text'),
    (MAIL_TYPE_HTML, 'HTML'),
]

FORWARD_STYLE_HEADERS = 'headers'
FORWARD_STYLE_QUOTE = 'quote'
FORWARD_STYLE_CHOICES = [
    (FORWARD_STYLE_HEADERS, 'Forwarded message header block'),
    (FORWARD_STYLE_QUOTE, 'Simple quoted message'),
]


class MailSettings(models.Model):
    """Site-wide preferences for the internal mail module (managed by HR)."""

    include_quote_in_reply = models.BooleanField(
        default=True,
        help_text='Show the sender\'s message under the reply box (Outlook-style).',
    )
    use_signature = models.BooleanField(default=False)
    signature = models.TextField(blank=True)
    default_mail_type = models.CharField(
        max_length=10, choices=MAIL_TYPE_CHOICES, default=MAIL_TYPE_PLAIN,
    )
    forward_style = models.CharField(
        max_length=10, choices=FORWARD_STYLE_CHOICES, default=FORWARD_STYLE_HEADERS,
    )

    def __str__(self):
        return 'Mail settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


FEATURE_MAIL = 'mail'
FEATURE_CHAT = 'chat'
FEATURE_MEETINGS = 'meetings'
FEATURE_CHOICES = [
    (FEATURE_MAIL, 'Mail'),
    (FEATURE_CHAT, 'Chat'),
    (FEATURE_MEETINGS, 'Meetings'),
]

_BLOCK_FIELDS = {
    FEATURE_MAIL: 'block_mail',
    FEATURE_CHAT: 'block_chat',
    FEATURE_MEETINGS: 'block_meetings',
}


class CollabAccess(models.Model):
    """Per-employee allow/block overrides for collaboration features.

    Managed by the Networks/IT team. Absence of a row means the employee
    has full access (default-on), so this table only stores exceptions.
    """

    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name='collab_access',
    )
    block_mail = models.BooleanField(default=False)
    block_chat = models.BooleanField(default=False)
    block_meetings = models.BooleanField(default=False)
    blocked_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Collaboration access'

    def __str__(self):
        blocked = [f for f in FEATURE_CHOICES if getattr(self, _BLOCK_FIELDS[f[0]])]
        return f'{self.employee} — blocked: {", ".join(b[0] for b in blocked) or "none"}'

    @property
    def blocked_features(self):
        return [f for f, field in _BLOCK_FIELDS.items() if getattr(self, field)]

    @property
    def is_fully_allowed(self):
        return not any(getattr(self, field) for field in _BLOCK_FIELDS.values())

    def set_block(self, feature, blocked, blocked_by=None):
        """Set/clear one feature block; delete the row when nothing is blocked."""
        field = _BLOCK_FIELDS.get(feature)
        if field is None:
            raise ValueError(f'Unknown feature: {feature}')
        setattr(self, field, blocked)
        if blocked and blocked_by is not None:
            self.blocked_by = blocked_by
        if self.is_fully_allowed and self.pk:
            self.delete()
            return None
        self.save()
        return self


def block_field(feature):
    """Return the ``block_<feature>`` field name for a feature key."""
    return _BLOCK_FIELDS[feature]


class MailMessage(models.Model):
    """An internal mail (Outlook-like). One row per sent message."""

    sender = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mails_sent',
    )
    subject = models.CharField(max_length=300)
    body = models.TextField()
    mail_type = models.CharField(max_length=10, choices=MAIL_TYPE_CHOICES, default=MAIL_TYPE_PLAIN)
    quoted = models.TextField(
        blank=True,
        help_text='Sanitized HTML of the quoted message shown under the reply (Outlook-style).',
    )
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.subject

    @property
    def to_employees(self):
        return [r.employee for r in self.recipients.all() if r.kind == 'to']

    @property
    def cc_employees(self):
        return [r.employee for r in self.recipients.all() if r.kind == 'cc']


class MailRecipient(models.Model):
    KIND_TO = 'to'
    KIND_CC = 'cc'
    KIND_CHOICES = [
        (KIND_TO, 'To'),
        (KIND_CC, 'CC'),
    ]

    mail = models.ForeignKey(MailMessage, on_delete=models.CASCADE, related_name='recipients')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='mails_received')
    kind = models.CharField(max_length=2, choices=KIND_CHOICES, default=KIND_TO)
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
