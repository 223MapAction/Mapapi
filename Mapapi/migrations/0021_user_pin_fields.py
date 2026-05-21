from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0020_chathistory_incident_chat'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='pin_code',
            field=models.CharField(
                blank=True,
                help_text='PIN hashé pour la connexion des agents de terrain (4 chiffres).',
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='must_change_pin',
            field=models.BooleanField(
                default=False,
                help_text="Si True, l'agent doit changer son PIN à la prochaine connexion.",
            ),
        ),
    ]
