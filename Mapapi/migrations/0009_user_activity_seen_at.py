from django.db import migrations, models


class Migration(migrations.Migration):
    """Ajoute User.activity_seen_at : horodatage de dernière consultation du flux
    d'activité, pour exposer des compteurs vues / non-vues (comme lu/non-lu des
    notifications)."""

    dependencies = [
        ('Mapapi', '0008_unaccent_extension'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='activity_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
