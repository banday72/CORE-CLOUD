from django.contrib.auth.models import User
from django.db import models

from employees.models import AuditLog

SEVERITY_CHOICES = [
    ('info', 'Info'), ('low', 'Low'), ('medium', 'Medium'),
    ('high', 'High'), ('critical', 'Critical'),
]


class DetectionRule(models.Model):
    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    window_minutes = models.PositiveIntegerField(default=15)
    threshold = models.PositiveIntegerField(default=5)
    params = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    auto_response = models.BooleanField(
        default=False,
        help_text='Run automated playbooks (lock account, revoke sessions, open ticket) when this rule fires.')

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.name


class Incident(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'), ('triaging', 'Triaging'), ('contained', 'Contained'),
        ('resolved', 'Resolved'), ('closed', 'Closed'),
    ]
    TEAM_CHOICES = [('networks', 'Networks'), ('software', 'Software'), ('hardware', 'Hardware')]

    title = models.CharField(max_length=200)
    detail = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='high')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='soc_incidents')
    team = models.CharField(max_length=15, choices=TEAM_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.title}'

    @property
    def is_open(self):
        return self.status not in ('resolved', 'closed')


class Alert(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'), ('acknowledged', 'Acknowledged'), ('closed', 'Closed'),
    ]

    rule = models.ForeignKey(DetectionRule, on_delete=models.PROTECT, related_name='alerts')
    title = models.CharField(max_length=200)
    detail = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='new')
    fingerprint = models.CharField(max_length=64, db_index=True)
    count = models.PositiveIntegerField(default=1)
    subject_username = models.CharField(
        max_length=150, blank=True,
        help_text='User/employee the alert is about (used by response playbooks).')
    event = models.ForeignKey(
        AuditLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts')
    incident = models.ForeignKey(
        Incident, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts')
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='soc_alerts')
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_seen']

    def __str__(self):
        return f'{self.title} ({self.get_severity_display()})'


class IncidentNote(models.Model):
    KIND_CHOICES = [
        ('comment', 'Comment'), ('status_change', 'Status Change'), ('auto_action', 'Auto Action'),
    ]

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='soc_notes')
    kind = models.CharField(max_length=15, choices=KIND_CHOICES, default='comment')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.incident_id}: {self.kind}'


class SOCIPEntry(models.Model):
    LIST_CHOICES = [('whitelist', 'Whitelist'), ('blacklist', 'Blacklist')]

    ip_address = models.GenericIPAddressField(unique=True)
    list_type = models.CharField(max_length=10, choices=LIST_CHOICES)
    reason = models.CharField(max_length=200, blank=True)
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='soc_ip_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.ip_address} ({self.get_list_type_display()})'


class SOCUserEntry(models.Model):
    """Whitelist/blacklist for user accounts: blacklist blocks all logins."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='soc_list_entry')
    list_type = models.CharField(max_length=10, choices=SOCIPEntry.LIST_CHOICES)
    reason = models.CharField(max_length=200, blank=True)
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='soc_user_entries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} ({self.get_list_type_display()})'


def user_is_blacklisted(username):
    if not username:
        return False
    return SOCUserEntry.objects.filter(
        user__username=username, list_type='blacklist').exists()


class ResponseAction(models.Model):
    ACTION_CHOICES = [
        ('lock_account', 'Lock account'),
        ('unlock_account', 'Unlock account'),
        ('revoke_sessions', 'Revoke sessions'),
        ('open_ticket', 'Open ticket'),
        ('notify', 'Notify team'),
    ]

    alert = models.ForeignKey(
        Alert, on_delete=models.CASCADE, null=True, blank=True, related_name='actions')
    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, null=True, blank=True, related_name='actions')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    params = models.JSONField(default=dict, blank=True)
    result = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    actor = models.CharField(max_length=150, default='system')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} by {self.actor}'
