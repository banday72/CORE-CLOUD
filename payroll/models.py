from django.db import models
from employees.models import Employee
import uuid


class PayrollPolicy(models.Model):
    name = models.CharField(max_length=100, default='Default Policy')
    working_days_per_month = models.IntegerField(default=30, help_text='Total working days in a month')
    absent_deduction_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=100.00, help_text='Fixed deduction per absent day (leave 0 to use per-day salary)')
    use_per_day_salary_for_absent = models.BooleanField(default=True, help_text='If checked, absent deduction = daily salary. If unchecked, uses fixed amount above')
    half_day_deduction_percent = models.IntegerField(default=50, help_text='Percentage of daily salary deducted for half day (0-100)')
    late_allowed_per_month = models.IntegerField(default=3, help_text='Number of late arrivals allowed per month without deduction')
    late_deduction_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Fixed deduction per late beyond allowed limit')
    approved_leave_paid = models.BooleanField(default=True, help_text='Are approved leaves fully paid?')
    tax_rate_percent = models.IntegerField(default=10, help_text='Tax percentage on gross salary')
    performance_bonus_enabled = models.BooleanField(default=True, help_text='Enable attendance-based performance bonus')
    bonus_100_percent = models.IntegerField(default=10, help_text='Bonus % for 100% attendance')
    bonus_95_percent = models.IntegerField(default=5, help_text='Bonus % for 95-99% attendance')
    bonus_90_percent = models.IntegerField(default=2, help_text='Bonus % for 90-94% attendance')
    bonus_below_90_percent = models.IntegerField(default=0, help_text='Bonus % for below 90% attendance')
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Monthly medical allowance')
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Monthly transport allowance')
    house_allowance_percent = models.IntegerField(default=0, help_text='House rent allowance as % of basic salary')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.working_days_per_month} days)"

    class Meta:
        ordering = ['-is_active', '-created_at']


class PayrollBreakdown(models.Model):
    payroll = models.OneToOneField('Payroll', on_delete=models.CASCADE, related_name='breakdown')
    total_working_days = models.IntegerField(default=30)
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    days_half_day = models.IntegerField(default=0)
    days_late = models.IntegerField(default=0)
    days_holiday = models.IntegerField(default=0)
    days_approved_leave = models.IntegerField(default=0)
    per_day_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    basic_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Salary earned based on attendance')
    attendance_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Deduction for absent/half-day')
    late_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Deduction for late arrivals')
    performance_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Bonus based on attendance %')
    bonus_percentage = models.IntegerField(default=0, help_text='Bonus percentage applied')
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    house_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_allowances_computed = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_computed = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Breakdown for {self.payroll}"

    class Meta:
        verbose_name_plural = 'Payroll Breakdowns'


class Payroll(models.Model):
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    GENERATED_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('auto', 'Auto Generated'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField()
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    generated_type = models.CharField(max_length=10, choices=GENERATED_TYPE_CHOICES, default='manual')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.get_month_display()} {self.year} - ${self.net_salary}"

    def calculate_net_salary(self):
        self.net_salary = self.basic_salary + self.allowances - self.deductions - self.tax
        return self.net_salary

    class Meta:
        unique_together = ['employee', 'month', 'year']
        ordering = ['-year', '-month']


class BoutiqueProduct(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ${self.price} (Stock: {self.stock})"

    class Meta:
        ordering = ['name']


class BoutiqueIssue(models.Model):
    product = models.ForeignKey(BoutiqueProduct, on_delete=models.CASCADE, related_name='issues')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='boutique_issues')
    quantity = models.IntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    issue_date = models.DateField()
    is_deducted = models.BooleanField(default=False)
    deducted_in_payroll = models.ForeignKey('Payroll', null=True, blank=True, on_delete=models.SET_NULL, related_name='boutique_deductions')
    issued_by = models.CharField(max_length=100, blank=True, help_text='Boutique manager name')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.employee_id} - {self.product.name} x{self.quantity} (${self.total_price})"

    def save(self, *args, **kwargs):
        self.total_price = self.product.price * self.quantity
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-issue_date']


class BudgetLoan(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='budget_loans')
    loan_amount = models.DecimalField(max_digits=10, decimal_places=2)
    monthly_deduction = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    total_deducted = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.employee_id} - Loan ${self.loan_amount} (${self.remaining_amount} remaining)"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.remaining_amount = self.loan_amount
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']


class PublicPayrollLink(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='public_link')
    token = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Public link for {self.employee.employee_id}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = str(uuid.uuid4())
        super().save(*args, **kwargs)
