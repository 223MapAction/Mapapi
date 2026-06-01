from django.db import migrations, models

from backend.supabase_storage import ImageStorage


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0022_user_type_field_agent'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='organisation',
            name='logo_url',
        ),
        migrations.AddField(
            model_name='organisation',
            name='logo',
            field=models.ImageField(
                blank=True,
                null=True,
                storage=ImageStorage(),
                upload_to='organisations/logos/',
                help_text="Logo de l'organisation (upload).",
            ),
        ),
    ]
