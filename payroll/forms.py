from django import forms
from .models import Payroll, PayrollPolicy, BoutiqueProduct, BoutiqueIssue, BudgetLoan
from employees.models import Employee


class PayrollForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ['employee', 'month', 'year', 'basic_salary', 'allowances',
                  'deductions', 'tax', 'status', 'payment_date', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'month': forms.Select(attrs={'class': 'form-select'}, choices=[
                (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
                (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
                (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
            ]),
            'year': forms.NumberInput(attrs={'class': 'form-control'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'allowances': forms.NumberInput(attrs={'class': 'form-control'}),
            'deductions': forms.NumberInput(attrs={'class': 'form-control'}),
            'tax': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class PayrollFilterForm(forms.Form):
    month = forms.ChoiceField(
        required=False,
        choices=[('', 'All Months')] + [
            (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
            (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
            (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
        ],
        widget=forms.Select(attrs={'class': 'form-select', 'data-autosubmit': True})
    )
    year = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Year', 'data-autosubmit': True})
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All')] + Payroll.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'data-autosubmit': True})
    )


class PayrollPolicyForm(forms.ModelForm):
    class Meta:
        model = PayrollPolicy
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'working_days_per_month': forms.NumberInput(attrs={'class': 'form-control'}),
            'absent_deduction_per_day': forms.NumberInput(attrs={'class': 'form-control'}),
            'use_per_day_salary_for_absent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'half_day_deduction_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'late_allowed_per_month': forms.NumberInput(attrs={'class': 'form-control'}),
            'late_deduction_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'approved_leave_paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tax_rate_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'performance_bonus_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'bonus_100_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'bonus_95_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'bonus_90_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'bonus_below_90_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'medical_allowance': forms.NumberInput(attrs={'class': 'form-control'}),
            'transport_allowance': forms.NumberInput(attrs={'class': 'form-control'}),
            'house_allowance_percent': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BoutiqueProductForm(forms.ModelForm):
    class Meta:
        model = BoutiqueProduct
        fields = ['name', 'price', 'stock', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Shirt, Laptop, Chair'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Product description...'}),
        }


class BoutiqueIssueForm(forms.ModelForm):
    class Meta:
        model = BoutiqueIssue
        fields = ['product', 'employee', 'quantity', 'issue_date', 'issued_by', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'data-autosubmit': True}),
            'employee': forms.Select(attrs={'class': 'form-select', 'data-autosubmit': True}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'issued_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Boutique manager name'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes...'}),
        }


class BudgetLoanForm(forms.ModelForm):
    class Meta:
        model = BudgetLoan
        fields = ['employee', 'loan_amount', 'monthly_deduction', 'reason', 'start_date', 'end_date']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select', 'data-autosubmit': True}),
            'loan_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'monthly_deduction': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Emergency loan, Advance salary'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
