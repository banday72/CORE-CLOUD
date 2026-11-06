from django import forms

from .models import LeaveType, Leave, count_business_days


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ['name', 'days_per_year', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'days_per_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class LeaveForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if not start or not end:
            return cleaned
        if end < start:
            self.add_error('end_date', 'End date must be on or after the start date.')
            return cleaned
        if count_business_days(start, end) == 0:
            self.add_error('end_date', 'The selected range contains no working days.')
            return cleaned
        employee = cleaned.get('employee')
        if employee:
            overlaps = Leave.objects.filter(
                employee=employee,
                status__in=['pending', 'approved'],
                start_date__lte=end,
                end_date__gte=start,
            )
            if self.instance and self.instance.pk:
                overlaps = overlaps.exclude(pk=self.instance.pk)
            if overlaps.exists():
                self.add_error('start_date', 'An existing leave request overlaps these dates.')
        return cleaned


class LeaveApprovalForm(forms.Form):
    STATUS_CHOICES = [('approved', 'Approve'), ('rejected', 'Reject')]
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    approved_by = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Name'})
    )