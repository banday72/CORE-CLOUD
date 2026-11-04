import uuid
from django.db import models
from employees.models import Employee


class PublicPayrollLink(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='public_link')
    token = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Public link for {self.employee.employee_id}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4()
        super().save(*args, **kwargs)
