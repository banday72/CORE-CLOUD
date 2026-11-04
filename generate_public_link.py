import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_payroll.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from employees.models import Employee
from payroll.models import PublicPayrollLink

emp = Employee.objects.filter(employee_id='EMP001').first()
if not emp:
    print("EMP001 not found. Run seed_data.py first.")
    sys.exit(1)

link, created = PublicPayrollLink.objects.get_or_create(employee=emp, defaults={'is_active': True})
if not link.token:
    import uuid
    link.token = str(uuid.uuid4())
    link.save()

print(f"\nPublic payslip link for EMP001 ({emp.first_name} {emp.last_name}):")
print(f"Token: {link.token}")
print(f"\nURL: /payroll/p/EMP001/{link.token}/")
print(f"\nFull URL (Vercel): https://corecloud-banday.vercel.app/payroll/p/EMP001/{link.token}/")
