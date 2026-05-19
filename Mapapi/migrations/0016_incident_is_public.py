"""Lot 2 — Ajout du champ is_public sur Incident."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0015_user_organisation_member_org_role_agent_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='incident',
            name='is_public',
            field=models.BooleanField(
                default=True,
                help_text="Si False, l'incident n'est visible que par l'organisation de l'agent.",
            ),
        ),
    ]
