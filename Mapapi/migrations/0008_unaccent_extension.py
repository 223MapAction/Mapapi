from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Active l'extension Postgres `unaccent` (recherche insensible aux accents).

    Crée l'extension dans le schéma `public` (présent dans le search_path en dev
    comme en prod) afin que le lookup Django `__unaccent` — qui appelle
    `UNACCENT()` sans qualifier le schéma — se résolve dans tous les environnements.
    Idempotent (CREATE EXTENSION IF NOT EXISTS).
    """

    dependencies = [
        ('Mapapi', '0007_notification_notif_type'),
    ]

    operations = [
        UnaccentExtension(),
    ]
