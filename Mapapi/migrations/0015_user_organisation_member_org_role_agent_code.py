"""Lot 1 — Ajout organisation_member (FK), org_role et agent_code sur User.

Includes a data migration to populate organisation_member from the existing
organisation CharField.
"""
from django.db import migrations, models
import django.db.models.deletion


def migrate_org_string_to_fk(apps, schema_editor):
    """Copie les valeurs du CharField 'organisation' vers la FK 'organisation_member'.

    Pour chaque user ayant un champ 'organisation' non vide :
      - Cherche ou crée l'Organisation correspondante ;
      - Affecte la FK ;
      - Si user_type == 'elu', met org_role = 'org_admin'.
    """
    User = apps.get_model('Mapapi', 'User')
    Organisation = apps.get_model('Mapapi', 'Organisation')

    for user in User.objects.exclude(organisation__isnull=True).exclude(organisation=''):
        org_name = user.organisation.strip()
        if not org_name:
            continue

        org, _created = Organisation.objects.get_or_create(
            name=org_name,
            defaults={
                'subdomain': org_name.lower().replace(' ', '-').replace("'", ''),
            },
        )
        user.organisation_member = org
        if user.user_type == 'elu':
            user.org_role = 'org_admin'
        user.save(update_fields=['organisation_member', 'org_role'])


def reverse_migration(apps, schema_editor):
    """Reverse : copie organisation_member.name vers le CharField."""
    User = apps.get_model('Mapapi', 'User')
    for user in User.objects.filter(organisation_member__isnull=False):
        user.organisation = user.organisation_member.name
        user.save(update_fields=['organisation'])


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0014_collaboration_role_discussionmessage_attachment_and_more'),
    ]

    operations = [
        # 1. Ajouter les 3 nouveaux champs
        migrations.AddField(
            model_name='user',
            name='organisation_member',
            field=models.ForeignKey(
                blank=True,
                help_text="Organisation à laquelle appartient l'utilisateur.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='members',
                to='Mapapi.organisation',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='org_role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('org_admin', 'Admin organisation'),
                    ('bureau_agent', 'Agent de bureau'),
                    ('field_agent', 'Agent de terrain'),
                ],
                help_text="Rôle interne dans l'organisation (org_admin, bureau_agent, field_agent).",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='agent_code',
            field=models.CharField(
                blank=True,
                help_text='Code auto-généré pour la connexion des agents de terrain.',
                max_length=10,
                null=True,
                unique=True,
            ),
        ),
        # 2. Data migration : copier organisation → organisation_member
        migrations.RunPython(migrate_org_string_to_fk, reverse_migration),
    ]
