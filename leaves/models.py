from datetime import date, timedelta

from django.db import models

from employees.models import Employee


def count_business_days(start, end):
    """Number of weekdays (Mon-Fri) in the inclusive ``start``..``end`` range."""
    if not start or not end or end < start:
        return 0
    total = 0
    current = start
    step = timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:
            total += 1
        current += step
    return total


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
        return count_business_days(self.start_date, self.end_date)

    def used_days(self, year=None):
        """Business days consumed from the annual balance for this leave type."""
        qs = Leave.objects.filter(
            employee=self.employee, leave_type=self.leave_type, status='approved')
        if year:
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            qs = qs.filter(start_date__lte=year_end, end_date__gte=year_start)
        total = 0
        for leave in qs:
            start, end = leave.start_date, leave.end_date
            if year:
                start = max(start, date(year, 1, 1))
                end = min(end, date(year, 12, 31))
            total += count_business_days(start, end)
        return total

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
        year_start = date(self.year, 1, 1)
        year_end = date(self.year, 12, 31)
        leaves = Leave.objects.filter(
            employee=self.employee, leave_type=self.leave_type,
            status='approved', start_date__lte=year_end, end_date__gte=year_start,
        )
        total = 0
        for leave in leaves:
            start = max(leave.start_date, year_start)
            end = min(leave.end_date, year_end)
            total += count_business_days(start, end)
        return total

    @property
    def remaining(self):
        return max(self.allocated - self.used, 0)

    class Meta:
        unique_together = ['employee', 'leave_type', 'year']
        ordering = ['leave_type__name']
