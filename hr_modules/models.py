from django.db import models
from django.utils import timezone
from employees.models import Employee
from datetime import timedelta
import uuid


class Notification(models.Model):
    TYPE_CHOICES = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notif_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.title}"

    class Meta:
        ordering = ['-created_at']


class EmployeeDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ('cnic', 'CNIC'),
        ('degree', 'Degree'),
        ('experience', 'Experience Letter'),
        ('contract', 'Employment Contract'),
        ('offer', 'Offer Letter'),
        ('noc', 'NOC'),
        ('other', 'Other'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    file_data = models.TextField(help_text='Base64 encoded file content')
    file_name = models.CharField(max_length=200)
    file_size = models.IntegerField(default=0, help_text='File size in bytes')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.get_doc_type_display()}: {self.title}"

    class Meta:
        ordering = ['-uploaded_at']


class PerformanceReview(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
    PERIOD_CHOICES = [
        ('Q1', 'Q1 (Jan-Mar)'),
        ('Q2', 'Q2 (Apr-Jun)'),
        ('Q3', 'Q3 (Jul-Sep)'),
        ('Q4', 'Q4 (Oct-Dec)'),
        ('annual', 'Annual'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='reviews_given')
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES)
    year = models.IntegerField()
    technical_score = models.IntegerField(choices=RATING_CHOICES, default=3)
    communication_score = models.IntegerField(choices=RATING_CHOICES, default=3)
    teamwork_score = models.IntegerField(choices=RATING_CHOICES, default=3)
    leadership_score = models.IntegerField(choices=RATING_CHOICES, default=3)
    initiative_score = models.IntegerField(choices=RATING_CHOICES, default=3)
    overall_rating = models.DecimalField(max_digits=3, decimal_places=2, default=3.0)
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    goals = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[('draft', 'Draft'), ('completed', 'Completed')], default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        scores = [self.technical_score, self.communication_score, self.teamwork_score,
                  self.leadership_score, self.initiative_score]
        self.overall_rating = sum(scores) / len(scores)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.get_period_display()} {self.year}: {self.overall_rating}"

    class Meta:
        unique_together = ['employee', 'period', 'year']
        ordering = ['-year', '-created_at']


class Training(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    provider = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    created_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='trainings_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    class Meta:
        ordering = ['-start_date']


class TrainingEnrollment(models.Model):
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
    ]
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name='enrollments')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='trainings')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')
    completion_date = models.DateField(null=True, blank=True)
    certificate = models.TextField(blank=True, help_text='Base64 encoded certificate')
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.training.title}"

    class Meta:
        unique_together = ['training', 'employee']


class TravelRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='travel_requests')
    destination = models.CharField(max_length=200)
    purpose = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='travels_approved')
    receipt_data = models.TextField(blank=True, help_text='Base64 encoded receipt')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.destination} ({self.get_status_display()})"

    class Meta:
        ordering = ['-created_at']


class NetworkTicket(models.Model):
    CATEGORY_CHOICES = [
        ('networks', 'Networks / Connectivity'),
        ('software', 'Software'),
        ('hardware', 'Hardware'),
        ('peripherals', 'Printers / Peripherals'),
        ('email', 'Email / Accounts'),
        ('security', 'Security / Access'),
        ('other', 'Other'),
    ]
    TEAM_CHOICES = [
        ('networks', 'Networks Team'),
        ('software', 'Software Team'),
        ('hardware', 'Hardware Team'),
    ]
    CATEGORY_TEAM = {
        'networks': 'networks',
        'security': 'networks',
        'email': 'networks',
        'other': 'networks',
        'software': 'software',
        'hardware': 'hardware',
        'peripherals': 'hardware',
    }
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Open (IT & Networks)'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]
    SLA_HOURS = {'urgent': 4, 'high': 8, 'medium': 24, 'low': 48}
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='network_tickets')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='networks')
    assigned_team = models.CharField(max_length=20, choices=TEAM_CHOICES, default='networks')
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_tickets_assigned')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_tickets_approved')
    resolved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_tickets_resolved')
    resolution_notes = models.TextField(blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def team_for_category(cls, category):
        return cls.CATEGORY_TEAM.get(category, 'networks')

    def save(self, *args, **kwargs):
        if not self.pk and not self.sla_due_at:
            self.sla_due_at = timezone.now() + timedelta(hours=self.SLA_HOURS.get(self.priority, 24))
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return bool(self.sla_due_at and self.status not in ('resolved', 'rejected')
                    and timezone.now() > self.sla_due_at)

    @property
    def sla_hours_left(self):
        if not self.sla_due_at:
            return None
        return round((self.sla_due_at - timezone.now()).total_seconds() / 3600, 1)

    @property
    def resolution_hours(self):
        if not self.resolved_at:
            return None
        return round((self.resolved_at - self.created_at).total_seconds() / 3600, 1)

    def __str__(self):
        return f"#{self.pk} {self.subject} - {self.get_status_display()}"

    class Meta:
        ordering = ['-created_at']


class TicketReply(models.Model):
    ticket = models.ForeignKey(NetworkTicket, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_replies')
    team = models.CharField(max_length=20, blank=True, help_text='Support team of the responder')
    message = models.TextField()
    is_internal = models.BooleanField(default=False, help_text='Internal note visible only to the assigned team')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply on #{self.ticket_id} by {self.author_id}"

    class Meta:
        ordering = ['created_at']


class OvertimeRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='overtime_records')
    date = models.DateField()
    hours = models.DecimalField(max_digits=4, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='overtimes_approved')
    rate_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=1.5, help_text='Overtime rate multiplier')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.employee and self.hours:
            daily = self.employee.salary / 30 / 8
            self.amount = float(self.hours) * float(daily) * float(self.rate_multiplier)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.date} - {self.hours}h"

    class Meta:
        unique_together = ['employee', 'date']
        ordering = ['-date']


class Announcement(models.Model):
    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('important', 'Important'),
        ('urgent', 'Urgent'),
    ]
    title = models.CharField(max_length=200)
    body = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    posted_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='announcements')
    is_pinned = models.BooleanField(default=False)
    publish_from = models.DateField(null=True, blank=True)
    publish_until = models.DateField(null=True, blank=True)
    attachment_b64 = models.TextField(blank=True, help_text='Base64 encoded attachment (optional)')
    attachment_name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_active(self):
        from datetime import date
        today = date.today()
        if self.publish_from and self.publish_from > today:
            return False
        if self.publish_until and self.publish_until < today:
            return False
        return True

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-is_pinned', '-created_at']
