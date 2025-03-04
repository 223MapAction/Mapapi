# Generated by Django 4.2.7 on 2025-02-27 17:27

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0005_user_is_verified_user_otp_user_otp_expiration_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiscussionMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('collaboration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='Mapapi.collaboration')),
                ('incident', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='Mapapi.incident')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
