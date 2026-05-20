from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0017_incident_is_deleted_user_is_deleted_fieldreport'),
    ]

    operations = [
        migrations.AddField(
            model_name='organisation',
            name='acronym',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='organisation',
            name='activity_sector',
            field=models.CharField(blank=True, choices=[('humanitarian', 'Humanitaire'), ('humanitarian_coordination', 'Coordination humanitaire'), ('development', 'Développement'), ('child_protection', "Protection de l'enfance"), ('health', 'Santé'), ('nutrition_food_security', 'Nutrition et sécurité alimentaire'), ('development_humanitarian', 'Développement et humanitaire')], max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='organisation',
            name='organisation_type',
            field=models.CharField(blank=True, choices=[('ngo', 'ONG'), ('international_organisation', 'Organisation internationale'), ('governmental', 'Gouvernementale'), ('civil_society', 'Société civile')], max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='organisation',
            name='intervention_country',
            field=models.CharField(blank=True, choices=[('senegal', 'Sénégal'), ('mali', 'Mali'), ('guinea', 'Guinée'), ('burkina_faso', 'Burkina Faso'), ('niger', 'Niger'), ('cote_divoire', 'Côte d’Ivoire'), ('mauritania', 'Mauritanie')], max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='organisation',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='organisation',
            name='partner_status',
            field=models.CharField(choices=[('active', 'Actif'), ('inactive', 'Inactif')], default='active', max_length=20),
        ),
        migrations.AddField(
            model_name='organisation',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='organisation',
            name='website_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='IncidentAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deadline', models.DateTimeField()),
                ('status', models.CharField(choices=[('pending', 'En attente'), ('in_progress', 'En cours'), ('reported', 'Rapport effectué'), ('cancelled', 'Annulé')], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incident_assignments', to=settings.AUTH_USER_MODEL)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_incident_assignments', to=settings.AUTH_USER_MODEL)),
                ('incident', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='Mapapi.incident')),
            ],
            options={
                'ordering': ('deadline', '-created_at'),
                'unique_together': {('incident', 'agent')},
            },
        ),
    ]
