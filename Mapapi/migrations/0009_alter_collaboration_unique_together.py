# Generated by Django 4.2.7 on 2025-03-03 11:43

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0008_discussionmessage_recipient'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='collaboration',
            unique_together={('incident', 'user')},
        ),
    ]
