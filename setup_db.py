import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_payroll.settings')

import django
django.setup()

from django.core.management import call_command

print("Running migrations...")
call_command('migrate', '--run-syncdb')

print("Seeding data...")
call_command('seed_data')

print("Done!")
