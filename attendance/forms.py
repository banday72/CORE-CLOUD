from django import forms
from .models import Attendance


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['employee', 'date', 'clock_in', 'clock_out', 'status', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'clock_in': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'clock_out': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class AttendanceFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'data-autosubmit': True})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'data-autosubmit': True})
    )
    employee = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Employee ID', 'data-autosubmit': True})
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All')] + Attendance.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'data-autosubmit': True})
    )
