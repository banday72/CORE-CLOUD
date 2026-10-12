import re

from django.db import models
from django.contrib.auth.models import User

CHIEF_ABBREVS = ('ceo', 'coo', 'cio', 'cso', 'cfo', 'cto', 'cmo', 'chro')
CHIEF_PHRASES = ('chief', 'director', 'general manager')
CHIEF_KEYWORDS = CHIEF_ABBREVS + CHIEF_PHRASES
HR_DEPARTMENT_NAME = 'Human Resources'
MANAGEMENT_DEPARTMENT_NAMES = ('managment', 'management')


def is_chief_designation(designation):
    if not designation:
        return False
    words = re.sub(r'[^a-z0-9]+', ' ', designation.lower()).split()
    if not words:
        return False
    if set(words) & set(CHIEF_ABBREVS):
        return True
    text = ' '.join(words)
    return any(phrase in text for phrase in CHIEF_PHRASES)


def chief_id_prefix(designation):
    if not designation:
        return None
    words = re.sub(r'[^A-Za-z0-9]+', ' ', designation).split()
    if not words:
        return None
    acronyms = [word.upper() for word in words if word.lower() in CHIEF_ABBREVS]
    if acronyms:
        return acronyms[0]
    lowered = [word.lower() for word in words]
    if 'chief' in lowered:
        initials = ''.join(word[0].upper() for word in words if word.isalpha())
        if 2 <= len(initials) <= 5:
            return initials
    return None


def default_password_for(employee_id):
    match = re.match(r'^[A-Za-z]+', employee_id or '')
    if match and match.group(0).lower() in CHIEF_ABBREVS:
        return match.group(0).lower() + '1234'
    return 'employee123'


class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Employee(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female'), ('O', 'Other')]
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive'), ('terminated', 'Terminated')]
    ROLE_CHOICES = [('employee', 'Employee'), ('hr', 'HR'), ('manager', 'Manager')]
    SUPPORT_TEAM_CHOICES = [
        ('networks', 'Networks Team'),
        ('software', 'Software Team'),
        ('hardware', 'Hardware Team'),
    ]
    IT_ROLE_CHOICES = [
        ('', 'No IT role'),
        ('manager', 'Team Manager'),
        ('assistant_manager', 'Assistant Manager'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    employee_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    address = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    designation = models.CharField(max_length=100, blank=True)
    date_of_joining = models.DateField()
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    city = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    profile_picture_b64 = models.TextField(blank=True, help_text='Base64 encoded profile picture for Vercel')
    reports_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates', help_text='Direct manager this employee reports to')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    support_team = models.CharField(max_length=20, choices=SUPPORT_TEAM_CHOICES, blank=True, help_text='IT/Networks support team this employee belongs to')
    it_role = models.CharField(max_length=20, choices=IT_ROLE_CHOICES, blank=True, help_text='IT team managerial role (team via support_team)')
    is_it_manager = models.BooleanField(default=False, help_text='Overall IT manager: can manage IT teams and view analytics')
    is_authorized = models.BooleanField(default=False, help_text='Only authorized users can login')
    approved_by_manager = models.BooleanField(default=False, help_text='Manager must approve authorization')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_employees')
    approved_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False, help_text='Force password change on next login')
    face_data = models.TextField(blank=True, help_text='JSON encoded face descriptors for face lock')
    face_registered = models.BooleanField(default=False, help_text='Whether face is registered for face lock')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee_id} - {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_chief(self):
        return is_chief_designation(self.designation)

    @property
    def in_hr_department(self):
        return bool(self.department and self.department.name == HR_DEPARTMENT_NAME)

    @property
    def is_hr(self):
        return self.role in ('hr', 'manager') or self.is_chief or self.in_hr_department

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def permission_group(self):
        from .permissions import permission_group as _permission_group
        return _permission_group(self)

    @property
    def permissions(self):
        from .permissions import permissions_for
        return permissions_for(self)

    def has_perm(self, perm):
        return perm in self.permissions

    @property
    def default_password(self):
        return default_password_for(self.employee_id)

    class Meta:
        ordering = ['employee_id']


def managers_q():
    condition = models.Q(role__in=('manager', 'hr'))
    for keyword in CHIEF_ABBREVS:
        condition |= models.Q(
            designation__iregex=r'(^|[^a-z0-9])%s($|[^a-z0-9])' % re.escape(keyword))
    for keyword in CHIEF_PHRASES:
        condition |= models.Q(designation__icontains=keyword)
    return condition


def managers_queryset():
    return Employee.objects.filter(managers_q(), status='active').select_related('department')


class LoginSlide(models.Model):
    name = models.CharField(max_length=100, blank=True)
    picture_b64 = models.TextField(help_text='Base64 encoded background image (data URI)')
    picture_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Login background'
        verbose_name_plural = 'Login backgrounds'

    def __str__(self):
        return self.name or self.picture_name or 'Slide %d' % self.id


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('authorize', 'Authorize'),
        ('deauthorize', 'Deauthorize'),
        ('password_change', 'Password Change'),
        ('export', 'Export'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Audit Logs'
