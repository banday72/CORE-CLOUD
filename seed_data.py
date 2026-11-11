import os
import secrets
import sys
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_payroll.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth.models import User
from employees.models import Department, Employee
from attendance.models import Attendance
from leaves.models import LeaveType, Leave
from payroll.models import Payroll, PayrollPolicy, BoutiqueProduct, BoutiqueIssue, BudgetLoan
from datetime import date, time, timedelta
import calendar

def seed_password(env_name, label):
    """Use an env-provided password, otherwise generate a private random one."""
    value = os.environ.get(env_name)
    if value:
        return value
    return secrets.token_urlsafe(12)


print("Seeding database...")

# Create superuser
admin_username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
admin_email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@hrpayroll.com')
if not User.objects.filter(username=admin_username).exists():
    admin_password = seed_password('DJANGO_SUPERUSER_PASSWORD', admin_username)
    User.objects.create_superuser(admin_username, admin_email, admin_password)
    print(f"Created superuser: {admin_username}")

# Create departments
departments_data = [
    ('Human Resources', 'Manages recruitment, employee relations, and benefits'),
    ('Engineering', 'Software development and technical operations'),
    ('Finance', 'Financial planning, accounting, and budgeting'),
    ('Marketing', 'Brand management, advertising, and market research'),
    ('Operations', 'Day-to-day business operations and logistics'),
    ('Sales', 'Client acquisition and revenue generation'),
]
departments = {}
for name, desc in departments_data:
    dept, _ = Department.objects.get_or_create(name=name, defaults={'description': desc})
    departments[name] = dept
print(f"Created {len(departments)} departments")

# Create CEO
ceo_emp = None
if not Employee.objects.filter(employee_id='CEO001').exists():
    ceo_password = seed_password('SEED_CEO001_PASSWORD', 'CEO001')
    ceo_user, _ = User.objects.get_or_create(username='CEO001',
        defaults={'email': 'ahmed.banday@company.com', 'first_name': 'Ahmed', 'last_name': 'Banday'})
    ceo_user.set_password(ceo_password)
    ceo_user.save()
    ceo_emp = Employee.objects.create(
        employee_id='CEO001', first_name='Ahmed', last_name='Banday',
        email='ahmed.banday@company.com', phone='0300-0000000',
        designation='CEO', date_of_joining=date(2020, 1, 1),
        salary=500000, status='active', role='manager',
        is_authorized=True, approved_by_manager=True, must_change_password=True)
    ceo_emp.user = ceo_user
    ceo_emp.save()
    print("Created CEO: CEO001")
else:
    ceo_emp = Employee.objects.get(employee_id='CEO001')

# C-Level Officers (report to CEO)
def create_officer(emp_id, first, last, email, dept, designation, salary):
    emp, created = Employee.objects.get_or_create(
        employee_id=emp_id,
        defaults={
            'first_name': first, 'last_name': last, 'email': email,
            'department': departments[dept], 'designation': designation,
            'date_of_joining': date(2020, 6, 1), 'salary': salary,
            'status': 'active', 'role': 'manager', 'is_authorized': True,
            'approved_by_manager': True, 'reports_to': ceo_emp,
            'must_change_password': True,
        }
    )
    if created:
        password = seed_password(f'SEED_{emp_id}_PASSWORD', emp_id)
        user, _ = User.objects.get_or_create(username=emp_id,
            defaults={'email': email, 'first_name': first, 'last_name': last})
        user.set_password(password)
        user.save()
        emp.user = user
        emp.save()
        print(f"Created {designation}: {emp_id}")
    return emp

coo = create_officer('COO001', 'Ali', 'Raza', 'ali.raza@company.com',
    'Operations', 'Chief Operating Officer', 300000)

cio = create_officer('CIO001', 'Zainab', 'Ahmed', 'zainab.ahmed@company.com',
    'Engineering', 'Chief Information Officer', 300000)

cso = create_officer('CSO001', 'Bilal', 'Sheikh', 'bilal.sheikh@company.com',
    'Marketing', 'Chief Strategic Officer', 300000)

cfo = create_officer('CFO001', 'Usman', 'Tariq', 'usman.tariq@company.com',
    'Finance', 'Chief Financial Officer', 300000)

# Employees under COO
employees_data = [
    ('EMP001', 'Hamza', 'Tariq', 'hamza.tariq@company.com', 'M', 'Operations', 'Operations Manager', 85000, coo),
    ('EMP002', 'Kamran', 'Shah', 'kamran.shah@company.com', 'M', 'Operations', 'Operations Executive', 65000, coo),
    ('EMP003', 'Hira', 'Shah', 'hira.shah@company.com', 'F', 'Operations', 'Operations Coordinator', 58000, coo),
    # Employees under CIO
    ('EMP004', 'Ahmed', 'Khan', 'ahmed.khan@company.com', 'M', 'Engineering', 'Senior Developer', 85000, cio),
    ('EMP005', 'Fatima', 'Ali', 'fatima.ali@company.com', 'F', 'Engineering', 'Full Stack Developer', 80000, cio),
    ('EMP006', 'Omar', 'Raza', 'omar.raza@company.com', 'M', 'Engineering', 'DevOps Engineer', 82000, cio),
    # Employees under CSO
    ('EMP007', 'Sara', 'Malik', 'sara.malik@company.com', 'F', 'Marketing', 'Marketing Lead', 72000, cso),
    ('EMP008', 'Hassan', 'Iqbal', 'hassan.iqbal@company.com', 'M', 'Marketing', 'Brand Strategist', 70000, cso),
    ('EMP009', 'Ayesha', 'Noor', 'ayesha.noor@company.com', 'F', 'Sales', 'Sales Executive', 68000, cso),
    # Employees under CFO
    ('EMP010', 'Bilal', 'Ahmed', 'bilal.ahmed@company.com', 'M', 'Finance', 'Financial Analyst', 75000, cfo),
    ('EMP011', 'Zainab', 'Khan', 'zainab.khan@company.com', 'F', 'Finance', 'Accountant', 70000, cfo),
    ('EMP012', 'Usman', 'Ali', 'usman.ali@company.com', 'M', 'Human Resources', 'HR Manager', 80000, cfo),
]

employees = {}
for emp_id, first, last, email, gender, dept_name, designation, salary, mgr in employees_data:
    emp, created = Employee.objects.get_or_create(
        employee_id=emp_id,
        defaults={
            'first_name': first, 'last_name': last, 'email': email, 'gender': gender,
            'department': departments[dept_name], 'designation': designation,
            'date_of_joining': date(2023, 1, 15), 'salary': salary,
            'status': 'active', 'is_authorized': True,
            'role': 'hr' if dept_name == 'Human Resources' else 'employee',
            'reports_to': mgr, 'must_change_password': True,
        }
    )
    if not emp.user:
        user, uc = User.objects.get_or_create(username=emp_id,
            defaults={'email': email, 'first_name': first, 'last_name': last})
        if uc:
            password = seed_password(
                f'SEED_{emp_id}_PASSWORD',
                emp_id,
            )
            user.set_password(password)
            user.save()
        emp.user = user
        emp.save()
    employees[emp_id] = emp
print(f"Created {len(employees)} employees")

# Create leave types
leave_types_data = [
    ('Annual Leave', 20, 'Yearly vacation leave'),
    ('Sick Leave', 10, 'Medical leave'),
    ('Personal Leave', 5, 'Personal reasons'),
    ('Maternity Leave', 90, 'Maternity/paternity leave'),
]
leave_types = {}
for name, days, desc in leave_types_data:
    lt, _ = LeaveType.objects.get_or_create(name=name, defaults={'days_per_year': days, 'description': desc})
    leave_types[name] = lt
print(f"Created {len(leave_types)} leave types")

# Create attendance records
today = date(2026, 9, 8)
patterns = {
    'EMP001': ['present'] * 5 + ['late'] * 1 + ['present'],
    'EMP002': ['present'] * 4 + ['half_day'] * 1 + ['present'] * 2,
    'EMP003': ['present'] * 3 + ['absent'] * 1 + ['present'] * 2 + ['late'],
    'EMP004': ['present'] * 5 + ['holiday'] + ['present'],
    'EMP005': ['present'] * 6 + ['half_day'],
    'EMP006': ['present'] * 4 + ['late'] * 2 + ['present'],
    'EMP007': ['present'] * 3 + ['absent'] * 2 + ['present'] * 2,
    'EMP008': ['present'] * 5 + ['present'] * 2,
    'EMP009': ['present'] * 4 + ['half_day'] + ['late'] + ['present'],
    'EMP010': ['present'] * 2 + ['absent'] * 1 + ['present'] * 2 + ['half_day'] + ['present'],
    'EMP011': ['present'] * 5 + ['late'] + ['present'],
    'EMP012': ['present'] * 6 + ['half_day'],
}
for emp_id, emp in employees.items():
    pattern = patterns.get(emp_id, ['present'] * 7)
    for i in range(7):
        att_date = today - timedelta(days=i)
        status = pattern[i % len(pattern)]
        clock_in_time = time(9, 0) if status != 'absent' else None
        if status == 'late':
            import random
            clock_in_time = time(9, random.randint(15, 45))
        clock_out_time = time(17, 30) if status in ['present', 'late', 'half_day'] else None
        Attendance.objects.get_or_create(
            employee=emp, date=att_date,
            defaults={'clock_in': clock_in_time, 'clock_out': clock_out_time, 'status': status})
print("Created attendance records")

# Create leave requests
Leave.objects.get_or_create(
    employee=employees['EMP004'], leave_type=leave_types['Annual Leave'],
    start_date=date(2026, 9, 15), end_date=date(2026, 9, 20),
    defaults={'reason': 'Family vacation', 'status': 'approved', 'approved_by': 'Admin'})
Leave.objects.get_or_create(
    employee=employees['EMP010'], leave_type=leave_types['Sick Leave'],
    start_date=date(2026, 9, 10), end_date=date(2026, 9, 11),
    defaults={'reason': 'Medical appointment', 'status': 'pending'})
Leave.objects.get_or_create(
    employee=employees['EMP007'], leave_type=leave_types['Personal Leave'],
    start_date=date(2026, 9, 12), end_date=date(2026, 9, 12),
    defaults={'reason': 'Personal work', 'status': 'approved', 'approved_by': 'Admin'})
print("Created leave requests")

# Create payroll policy
PayrollPolicy.objects.get_or_create(
    name='Standard Company Policy',
    defaults={
        'working_days_per_month': 30, 'absent_deduction_per_day': 0,
        'use_per_day_salary_for_absent': True, 'half_day_deduction_percent': 50,
        'late_allowed_per_month': 3, 'late_deduction_amount': 500,
        'approved_leave_paid': True, 'tax_rate_percent': 10,
        'performance_bonus_enabled': True, 'bonus_100_percent': 10,
        'bonus_95_percent': 5, 'bonus_90_percent': 2, 'bonus_below_90_percent': 0,
        'medical_allowance': 5000, 'transport_allowance': 3000,
        'house_allowance_percent': 20, 'is_active': True})
print("Created payroll policy")

# Create payroll records
all_emps = list(employees.values())
for emp in all_emps:
    basic = emp.salary
    allowances = basic * Decimal('0.15')
    deductions = basic * Decimal('0.05')
    tax = basic * Decimal('0.10')
    net = basic + allowances - deductions - tax
    Payroll.objects.get_or_create(
        employee=emp, month=8, year=2026,
        defaults={
            'basic_salary': round(basic, 2), 'allowances': round(allowances, 2),
            'deductions': round(deductions, 2), 'tax': round(tax, 2),
            'net_salary': round(net, 2), 'status': 'paid',
            'payment_date': date(2026, 8, 28), 'generated_type': 'auto'})
print("Created payroll records")

# Print hierarchy
print("\n" + "=" * 60)
print("ORGANIZATION HIERARCHY")
print("=" * 60)
print("CEO001 - Ahmed Banday (CEO)")
print(f"|-- COO001 - Ali Raza (Chief Operating Officer)")
for eid in ['EMP001', 'EMP002', 'EMP003']:
    e = employees[eid]
    print(f"|   |-- {eid} - {e.first_name} {e.last_name} ({e.designation})")
print(f"|-- CIO001 - Zainab Ahmed (Chief Information Officer)")
for eid in ['EMP004', 'EMP005', 'EMP006']:
    e = employees[eid]
    print(f"|   |-- {eid} - {e.first_name} {e.last_name} ({e.designation})")
print(f"|-- CSO001 - Bilal Sheikh (Chief Strategic Officer)")
for eid in ['EMP007', 'EMP008', 'EMP009']:
    e = employees[eid]
    print(f"|   |-- {eid} - {e.first_name} {e.last_name} ({e.designation})")
print(f"`-- CFO001 - Usman Tariq (Chief Financial Officer)")
for eid in ['EMP010', 'EMP011', 'EMP012']:
    e = employees[eid]
    print(f"    |-- {eid} - {e.first_name} {e.last_name} ({e.designation})")
print("=" * 60)
print(f"\nLogins:")
print(f"Superadmin: {admin_username}")
print("Passwords are supplied through environment variables or generated privately.")
print(f"\nTotal: {Employee.objects.count()} employees, {Department.objects.count()} departments")
