# Generated by Django 4.2.7 on 2025-05-09 17:03

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0009_alter_collaboration_unique_together'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrganisationTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('incident_type', models.CharField(max_length=255)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incident_preferences', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
