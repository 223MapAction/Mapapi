# Generated by Django 4.2.7 on 2024-10-24 15:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prediction',
            name='prediction_id',
            field=models.CharField(blank=True, null=True, unique=True),
        ),
    ]
