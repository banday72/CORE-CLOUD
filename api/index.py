import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_payroll.settings')

import django
django.setup()

from django.core.management import call_command
try:
    call_command('migrate', '--run-syncdb', '--noinput', verbosity=0)
except Exception:
    pass


def seed_demo():
    from django.contrib.auth.models import User
    from employees.models import Employee, Department
    from datetime import date
    from django.db import transaction

    if not User.objects.filter(username='admin').exists() and os.environ.get('SEED_ADMIN_PASSWORD'):
        User.objects.create_superuser('admin', 'admin@hrpayroll.com',
                                      os.environ['SEED_ADMIN_PASSWORD'])

    depts = {}
    for name, desc in [
        ('Human Resources', 'HR Department'),
        ('Engineering', 'Software development'),
        ('Finance', 'Financial planning'),
        ('Marketing', 'Brand and advertising'),
        ('Operations', 'Day-to-day operations'),
        ('Sales', 'Revenue generation'),
    ]:
        d, _ = Department.objects.get_or_create(name=name, defaults={'description': desc})
        depts[name] = d

    def get_or_create_emp(emp_id, first, last, email, dept_name, designation, salary,
                          role='employee', reports_to=None, password='employee123', emp_type='EMP'):
        existing = Employee.objects.filter(employee_id=emp_id).select_related('user').first()
        if existing:
            return existing
        user, created = User.objects.get_or_create(
            username=emp_id,
            defaults={'email': email, 'first_name': first, 'last_name': last})
        if created:
            user.set_password(password)
            user.save()
        emp = Employee.objects.create(
            employee_id=emp_id, first_name=first, last_name=last,
            email=email, department=depts.get(dept_name),
            designation=designation, date_of_joining=date(2021, 1, 1),
            salary=salary, status='active', role=role,
            is_authorized=True, approved_by_manager=True,
            reports_to=reports_to)
        emp.user = user
        emp.save()
        return emp

    # Demo org chart (idempotent: never resets passwords of existing users).
    with transaction.atomic():
        ceo = get_or_create_emp('CEO001', 'Ahmed', 'Banday', 'ahmed.banday@company.com',
            'Operations', 'CEO', 500000, role='manager', password='ceo123')
        coo = get_or_create_emp('COO001', 'Ali', 'Raza', 'ali.raza@company.com',
            'Operations', 'Chief Operating Officer', 300000, role='manager', reports_to=ceo, password='coo123')
        cio = get_or_create_emp('CIO001', 'Zainab', 'Ahmed', 'zainab.ahmed@company.com',
            'Engineering', 'Chief Information Officer', 300000, role='manager', reports_to=ceo, password='cio123')
        cso = get_or_create_emp('CSO001', 'Bilal', 'Sheikh', 'bilal.sheikh@company.com',
            'Marketing', 'Chief Strategic Officer', 300000, role='manager', reports_to=ceo, password='cso123')
        cfo = get_or_create_emp('CFO001', 'Usman', 'Tariq', 'usman.tariq@company.com',
            'Finance', 'Chief Financial Officer', 300000, role='manager', reports_to=ceo, password='cfo123')
        get_or_create_emp('EMP001', 'Hamza', 'Tariq', 'hamza.tariq@company.com',
            'Operations', 'Operations Manager', 85000, reports_to=coo)
        get_or_create_emp('EMP002', 'Kamran', 'Shah', 'kamran.shah@company.com',
            'Operations', 'Operations Executive', 65000, reports_to=coo)
        get_or_create_emp('EMP003', 'Hira', 'Shah', 'hira.shah@company.com',
            'Operations', 'Operations Coordinator', 58000, reports_to=coo)
        get_or_create_emp('EMP004', 'Ahmed', 'Khan', 'ahmed.khan@company.com',
            'Engineering', 'Senior Developer', 85000, reports_to=cio)
        get_or_create_emp('EMP005', 'Fatima', 'Ali', 'fatima.ali@company.com',
            'Engineering', 'Full Stack Developer', 80000, reports_to=cio)
        get_or_create_emp('EMP006', 'Omar', 'Raza', 'omar.raza@company.com',
            'Engineering', 'DevOps Engineer', 82000, reports_to=cio)
        get_or_create_emp('EMP007', 'Sara', 'Malik', 'sara.malik@company.com',
            'Marketing', 'Marketing Lead', 72000, reports_to=cso)
        get_or_create_emp('EMP008', 'Hassan', 'Iqbal', 'hassan.iqbal@company.com',
            'Marketing', 'Brand Strategist', 70000, reports_to=cso)
        get_or_create_emp('EMP009', 'Ayesha', 'Noor', 'ayesha.noor@company.com',
            'Sales', 'Sales Executive', 68000, reports_to=cso)
        get_or_create_emp('EMP010', 'Bilal', 'Ahmed', 'bilal.ahmed@company.com',
            'Finance', 'Financial Analyst', 75000, reports_to=cfo)
        get_or_create_emp('EMP011', 'Zainab', 'Khan', 'zainab.khan@company.com',
            'Finance', 'Accountant', 70000, reports_to=cfo)
        get_or_create_emp('EMP012', 'Usman', 'Ali', 'usman.ali@company.com',
            'Human Resources', 'HR Manager', 80000, reports_to=cfo)

        from payroll.models import PublicPayrollLink
        emp001 = Employee.objects.filter(employee_id='EMP001').first()
        if emp001 and not PublicPayrollLink.objects.filter(employee=emp001).exists():
            PublicPayrollLink.objects.create(employee=emp001, is_active=True)


if os.environ.get('SEED_DEMO', 'False') == 'True':
    try:
        seed_demo()
    except Exception:
        pass

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

def handler(request):
    status_code = 200
    headers_dict = {}

    def start_response(status, headers, exc_info=None):
        nonlocal status_code, headers_dict
        status_code = int(status.split(' ', 1)[0])
        headers_dict = dict(headers)

    response_body = b''.join(application(request.environ, start_response))

    return {
        'statusCode': status_code,
        'headers': headers_dict,
        'body': response_body.decode('utf-8', errors='replace'),
    }
