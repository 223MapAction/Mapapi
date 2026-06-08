from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0024_incidenttask_is_confirmed'),
    ]

    operations = [
        migrations.AddField(
            model_name='incident',
            name='take_in_charge_mode',
            field=models.CharField(
                blank=True,
                choices=[
                    ('internal', 'Interne (organisation seule)'),
                    ('collaborative', 'Collaborative (ouvert aux autres organisations)'),
                ],
                help_text="Mode de prise en charge choisi par la première organisation.",
                max_length=20,
                null=True,
            ),
        ),
    ]
