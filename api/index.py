import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_payroll.settings')

import django
django.setup()

if os.environ.get('RUN_MIGRATIONS_ON_BOOT') == 'True':
    from django.core.management import call_command
    try:
        call_command('migrate', '--noinput', verbosity=0)
    except Exception:
        pass


def seed_demo():
    from django.contrib.auth.models import User
    from employees.models import Employee, Department, generate_temp_password
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
                          role='employee', reports_to=None, password=None, emp_type='EMP'):
        existing = Employee.objects.filter(employee_id=emp_id).select_related('user').first()
        if existing:
            return existing
        user, created = User.objects.get_or_create(
            username=emp_id,
            defaults={'email': email, 'first_name': first, 'last_name': last})
        if created:
            user.set_password(
                os.environ.get('SEED_DEMO_PASSWORD') or generate_temp_password())
            user.save()
        emp = Employee.objects.create(
            employee_id=emp_id, first_name=first, last_name=last,
            email=email, department=depts.get(dept_name),
            designation=designation, date_of_joining=date(2021, 1, 1),
            salary=salary, status='active', role=role,
            is_authorized=True, approved_by_manager=True,
            reports_to=reports_to, must_change_password=True)
        emp.user = user
        emp.save()
        return emp

    # Demo org chart (idempotent: never resets passwords of existing users).
    with transaction.atomic():
        ceo = get_or_create_emp('CEO001', 'Ahmed', 'Banday', 'ahmed.banday@company.com',
            'Operations', 'CEO', 500000, role='manager')
        coo = get_or_create_emp('COO001', 'Ali', 'Raza', 'ali.raza@company.com',
            'Operations', 'Chief Operating Officer', 300000, role='manager', reports_to=ceo)
        cio = get_or_create_emp('CIO001', 'Zainab', 'Ahmed', 'zainab.ahmed@company.com',
            'Engineering', 'Chief Information Officer', 300000, role='manager', reports_to=ceo)
        cso = get_or_create_emp('CSO001', 'Bilal', 'Sheikh', 'bilal.sheikh@company.com',
            'Marketing', 'Chief Strategic Officer', 300000, role='manager', reports_to=ceo)
        cfo = get_or_create_emp('CFO001', 'Usman', 'Tariq', 'usman.tariq@company.com',
            'Finance', 'Chief Financial Officer', 300000, role='manager', reports_to=ceo)
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




if os.environ.get('SEED_DEMO') == 'True' and os.environ.get('SEED_DEMO_PASSWORD'):
    try:
        seed_demo()
    except Exception:
        pass

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()
application = app


def handler(request):
    """Adapt Django's WSGI application to Vercel's Python function format."""
    status_code = 500
    headers = {}

    def start_response(status, response_headers, exc_info=None):
        nonlocal status_code, headers
        status_code = int(status.split(' ', 1)[0])
        headers = dict(response_headers)

    body = b''.join(application(request.environ, start_response))
    response = {
        'statusCode': status_code,
        'headers': headers,
        'body': body.decode('utf-8', errors='replace'),
    }
    return response
