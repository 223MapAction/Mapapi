# Generated manually for IVR models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0012_alter_evenement_audio_alter_evenement_photo_and_more'),  # Ajustez selon votre dernière migration
    ]

    operations = [
        migrations.CreateModel(
            name='IVRCall',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('call_sid', models.CharField(max_length=255, unique=True)),
                ('phone_number', models.CharField(max_length=20)),
                ('status', models.CharField(default='initiated', max_length=50)),
                ('zone_selected', models.CharField(blank=True, max_length=250, null=True)),
                ('description_audio_url', models.URLField(blank=True, null=True)),
                ('description_audio_duration', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category_selected', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Mapapi.category')),
                ('incident_created', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Mapapi.incident')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Mapapi.user')),
            ],
        ),
        migrations.CreateModel(
            name='IVRInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step', models.CharField(max_length=50)),
                ('user_input', models.CharField(blank=True, max_length=255, null=True)),
                ('recording_url', models.URLField(blank=True, null=True)),
                ('recording_duration', models.IntegerField(blank=True, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('ivr_call', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interactions', to='Mapapi.ivrcall')),
            ],
            options={
                'ordering': ['timestamp'],
            },
        ),
    ]
