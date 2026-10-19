from django.db import migrations

RULE = {
    'key': 'blacklist_hit',
    'name': 'Blacklisted IP activity',
    'description': 'Any event originating from a blacklisted IP (no threshold).',
    'severity': 'critical', 'window_minutes': 15, 'threshold': 1,
    'auto_response': False,
}


def seed(apps, schema_editor):
    DetectionRule = apps.get_model('soc', 'DetectionRule')
    DetectionRule.objects.get_or_create(key=RULE['key'], defaults=RULE)


def unseed(apps, schema_editor):
    DetectionRule = apps.get_model('soc', 'DetectionRule')
    DetectionRule.objects.filter(key=RULE['key']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('soc', '0003_alter_responseaction_action_socipentry'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
