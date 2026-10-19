"""Run the SOC detection engine.

    python manage.py run_soc_rules             # seed rules + scan last 24h once
    python manage.py run_soc_rules --hours 48  # widen the scan window
    python manage.py run_soc_rules --seed-only # just ensure default rules exist
    python manage.py run_soc_rules --loop --interval 300   # local dev daemon
"""

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from soc.engine import run_scan


DEFAULT_RULES = [
    {
        'key': 'blacklist_hit',
        'name': 'Blacklisted IP activity',
        'description': 'Any event originating from a blacklisted IP (no threshold).',
        'severity': 'critical', 'window_minutes': 15, 'threshold': 1,
        'auto_response': False,
    },
    {
        'key': 'brute_force',
        'name': 'Brute force login attempts',
        'description': '5+ failed logins for the same account within 15 minutes.',
        'severity': 'critical', 'window_minutes': 15, 'threshold': 5,
        'auto_response': True,
    },
    {
        'key': 'credential_stuffing',
        'name': 'Credential stuffing',
        'description': '10+ failed logins across 3+ accounts from a single IP within 15 minutes.',
        'severity': 'critical', 'window_minutes': 15, 'threshold': 10,
        'params': {'min_users': 3}, 'auto_response': False,
    },
    {
        'key': 'account_lockout',
        'name': 'Account lockout',
        'description': 'An account was locked after repeated failed logins.',
        'severity': 'high', 'window_minutes': 30, 'threshold': 1,
        'auto_response': False,
    },
    {
        'key': 'suspicious_ip',
        'name': 'Suspicious IP activity',
        'description': 'One IP touches 5+ distinct accounts within 60 minutes.',
        'severity': 'high', 'window_minutes': 60, 'threshold': 5,
        'auto_response': False,
    },
    {
        'key': 'mass_export',
        'name': 'Mass data export',
        'description': '10+ CSV exports by the same user within 30 minutes.',
        'severity': 'high', 'window_minutes': 30, 'threshold': 10,
        'auto_response': False,
    },
    {
        'key': 'off_hours_admin',
        'name': 'Off-hours administration',
        'description': 'CRUD or authorize actions outside 06:00-22:00 UTC.',
        'severity': 'medium', 'window_minutes': 60, 'threshold': 1,
        'params': {'start_hour': 6, 'end_hour': 22},
        'auto_response': False,
    },
    {
        'key': 'privilege_change',
        'name': 'Privilege escalation',
        'description': 'A user was authorized or deauthorized.',
        'severity': 'medium', 'window_minutes': 60, 'threshold': 1,
        'auto_response': False,
    },
    {
        'key': 'ip_switch',
        'name': 'Impossible travel / IP switch',
        'description': 'Same account logs in from 2+ IPs within 30 minutes.',
        'severity': 'medium', 'window_minutes': 30, 'threshold': 2,
        'auto_response': False,
    },
    {
        'key': 'locked_attempt',
        'name': 'Login attempt on locked account',
        'description': 'Someone tried to log in while the account was locked.',
        'severity': 'high', 'window_minutes': 15, 'threshold': 1,
        'auto_response': False,
    },
]


def seed_rules():
    from soc.models import DetectionRule
    created = 0
    for spec in DEFAULT_RULES:
        _, was_created = DetectionRule.objects.get_or_create(
            key=spec['key'],
            defaults={k: v for k, v in spec.items() if k != 'key'},
        )
        created += int(was_created)
    return created


class Command(BaseCommand):
    help = 'Seed SOC detection rules and run the detection scan.'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24,
                            help='Scan window in hours (default 24).')
        parser.add_argument('--seed-only', action='store_true',
                            help='Only ensure default rules exist.')
        parser.add_argument('--loop', action='store_true',
                            help='Keep scanning forever (local dev).')
        parser.add_argument('--interval', type=int, default=300,
                            help='Seconds between scans in --loop mode.')

    def handle(self, *args, **options):
        created = seed_rules()
        if created:
            self.stdout.write(self.style.SUCCESS(f'Seeded {created} detection rule(s).'))
        if options['seed_only']:
            return
        if options['loop']:
            self.stdout.write('Scanning every %ss (Ctrl+C to stop)...' % options['interval'])
            while True:
                try:
                    n = run_scan(hours=options['hours'])
                    self.stdout.write(f'Scanned {n} events at {timezone.now():%H:%M:%S}')
                except Exception as exc:
                    self.stderr.write(f'Scan failed: {exc}')
                time.sleep(options['interval'])
        n = run_scan(hours=options['hours'])
        self.stdout.write(self.style.SUCCESS(f'Scanned {n} events (last {options["hours"]}h).'))
