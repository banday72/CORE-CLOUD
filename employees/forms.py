from django import forms
from django.contrib.auth.models import User
from .models import Department, Employee, managers_queryset


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class EmployeeForm(forms.ModelForm):
    FIELD_ORDER = [
        'employee_id_preview', 'first_name', 'last_name', 'email', 'phone',
        'department', 'designation', 'reports_to', 'salary', 'role', 'support_team', 'status',
    ]

    employee_id_preview = forms.CharField(
        label='Employee ID',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': True, 'placeholder': 'Auto-generated'}),
    )

    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'email', 'phone',
                  'date_of_birth', 'gender', 'address', 'city', 'department', 'designation',
                  'date_of_joining', 'salary', 'reports_to', 'role', 'support_team', 'status', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'reports_to': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'support_team': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'profile_picture': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        from .permissions import permissions_for_user
        user_permissions = permissions_for_user(user)
        if 'support_team' in self.fields and 'manage_it_teams' not in user_permissions:
            del self.fields['support_team']
        if 'status' in self.fields and 'manage_employee_status' not in user_permissions:
            del self.fields['status']
        self.order_fields([f for f in self.FIELD_ORDER if f in self.fields])
        if 'reports_to' in self.fields:
            instance = self.instance.pk if self.instance and self.instance.pk else None
            qs = managers_queryset()
            if instance:
                qs = qs.exclude(pk=instance)
            self.fields['reports_to'].queryset = qs
            self.fields['reports_to'].empty_label = 'No Manager'
            self.fields['reports_to'].label = 'Reports To (Manager)'


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class LoginSlideForm(forms.Form):
    name = forms.CharField(max_length=100, required=False, label='Slide name (optional)',
                           widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Office tower'}))
    picture = forms.ImageField(label='Background image',
                               widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))
    is_active = forms.BooleanField(required=False, initial=True,
                                   label='Active (shown on login page)')
    sort_order = forms.IntegerField(required=False, initial=0, min_value=0, max_value=999,
                                    label='Order (lowest first)',
                                    widget=forms.NumberInput(attrs={'class': 'form-control'}))
