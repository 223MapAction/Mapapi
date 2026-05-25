from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0021_user_pin_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='user_type',
            field=models.CharField(
                choices=[
                    ('admin', 'admin'),
                    ('visitor', 'visitor'),
                    ('reporter', 'reporter'),
                    ('citizen', 'citizen'),
                    ('business', 'business'),
                    ('elu', 'elu'),
                    ('field_agent', 'field_agent'),
                ],
                default='citizen',
                max_length=15,
            ),
        ),
    ]
