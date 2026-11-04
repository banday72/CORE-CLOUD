import os
import runpy
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hr_payroll.settings')

import django
django.setup()

from django.core.management import call_command

print("Running migrations...")
call_command('migrate', interactive=False)

print("Seeding data...")
runpy.run_path(str(BASE_DIR / 'seed_data.py'), run_name='__main__')

print("Done!")
