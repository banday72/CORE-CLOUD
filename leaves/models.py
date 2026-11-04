from django.db import models
from employees.models import Employee


class LeaveType(models.Model):
    name = models.CharField(max_length=100)
    days_per_year = models.IntegerField(default=12)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Leave(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name} ({self.start_date} to {self.end_date})"

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days + 1

    def used_days(self, year=None):
        """Days consumed from the employee's annual balance for this leave type."""
        qs = Leave.objects.filter(
            employee=self.employee, leave_type=self.leave_type, status='approved')
        if year:
            qs = qs.filter(start_date__year=year)
        return sum((l.end_date - l.start_date).days + 1 for l in qs)

    class Meta:
        ordering = ['-created_at']


class LeaveBalance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='balances')
    year = models.IntegerField()
    allocated = models.IntegerField(default=0, help_text='Days allocated for the year')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.leave_type.name} {self.year}"

    @property
    def used(self):
        return sum(
            (l.end_date - l.start_date).days + 1
            for l in Leave.objects.filter(
                employee=self.employee, leave_type=self.leave_type,
                status='approved', start_date__year=self.year,
            )
        )

    @property
    def remaining(self):
        return max(self.allocated - self.used, 0)

    class Meta:
        unique_together = ['employee', 'leave_type', 'year']
        ordering = ['leave_type__name']
