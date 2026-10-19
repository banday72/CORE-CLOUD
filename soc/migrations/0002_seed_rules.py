from django.db import migrations

DEFAULT_RULES = [
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


def seed_rules(apps, schema_editor):
    DetectionRule = apps.get_model('soc', 'DetectionRule')
    for spec in DEFAULT_RULES:
        DetectionRule.objects.get_or_create(
            key=spec['key'],
            defaults={k: v for k, v in spec.items() if k != 'key'},
        )


def unseed_rules(apps, schema_editor):
    DetectionRule = apps.get_model('soc', 'DetectionRule')
    DetectionRule.objects.filter(key__in=[r['key'] for r in DEFAULT_RULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('soc', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_rules, unseed_rules),
    ]
