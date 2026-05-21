from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0018_organisation_extra_fields_incidentassignment'),
    ]

    operations = [
        # --- Rename legacy CharField ``incident_id`` so it stops clashing
        # with the FK ``incident`` we are about to add (which auto-creates
        # an ``incident_id`` attribute/column).
        migrations.RenameField(
            model_name='prediction',
            old_name='incident_id',
            new_name='legacy_incident_id',
        ),
        # --- Make legacy fields nullable so the new flow can create rows
        # without filling all the historical columns.
        migrations.AlterField(
            model_name='prediction',
            name='legacy_incident_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='prediction',
            name='incident_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='prediction',
            name='piste_solution',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='prediction',
            name='analysis',
            field=models.TextField(blank=True, null=True),
        ),

        # --- New FK to Incident
        migrations.AddField(
            model_name='prediction',
            name='incident',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=models.deletion.CASCADE,
                related_name='prediction',
                to='Mapapi.incident',
            ),
        ),

        # --- Status
        migrations.AddField(
            model_name='prediction',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('completed', 'Completed'),
                    ('completed_with_warning', 'Completed with warning'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=32,
            ),
        ),

        # --- AI analysis
        migrations.AddField(model_name='prediction', name='macro_category',
                            field=models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField(model_name='prediction', name='sub_category',
                            field=models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField(model_name='prediction', name='description',
                            field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='prediction', name='source_size_meters',
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='spread_vectors',
                            field=models.JSONField(blank=True, default=list)),

        # --- Impact
        migrations.AddField(model_name='prediction', name='impact_radius_meters',
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='radius_explanation',
                            field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='prediction', name='global_impact_score',
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='base_severity',
                            field=models.IntegerField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='impact_tags',
                            field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name='prediction', name='recommendation',
                            field=models.TextField(blank=True, default='')),

        # --- Geo
        migrations.AddField(model_name='prediction', name='latitude',
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='longitude',
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='city',
                            field=models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField(model_name='prediction', name='region',
                            field=models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField(model_name='prediction', name='country',
                            field=models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField(model_name='prediction', name='display_name',
                            field=models.TextField(blank=True, default='')),

        # --- Social
        migrations.AddField(model_name='prediction', name='social_vulnerability_score',
                            field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='is_social_probabilistic',
                            field=models.BooleanField(default=False)),

        # --- Population
        migrations.AddField(model_name='prediction', name='total_population_exposed',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='adult_men_exposed',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='adult_women_exposed',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='children_exposed',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='maternities_count',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='nurseries_count',
                            field=models.IntegerField(default=0)),

        # --- Infrastructure
        migrations.AddField(model_name='prediction', name='health_centers',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='maternities',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='schools',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='nurseries',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='markets',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='water_points',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='main_roads_bridges',
                            field=models.IntegerField(default=0)),
        migrations.AddField(model_name='prediction', name='residential_buildings',
                            field=models.IntegerField(default=0)),

        # --- Raw blocks
        migrations.AddField(model_name='prediction', name='ai_analysis',
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='prediction', name='topography',
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='prediction', name='satellite',
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='prediction', name='social_data',
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='prediction', name='human_impact',
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='prediction', name='geocoding',
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='prediction', name='potential_risk',
                            field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name='prediction', name='full_response',
                            field=models.JSONField(blank=True, default=dict)),

        # --- Errors / timestamps
        migrations.AddField(model_name='prediction', name='error_message',
                            field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='prediction', name='created_at',
                            field=models.DateTimeField(auto_now_add=True, null=True)),
        migrations.AddField(model_name='prediction', name='updated_at',
                            field=models.DateTimeField(auto_now=True, null=True)),
    ]
