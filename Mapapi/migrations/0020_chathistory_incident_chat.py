from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Mapapi', '0019_prediction_extended'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Make legacy fields nullable so we can store role/content rows.
        migrations.AlterField(
            model_name='chathistory',
            name='session_id',
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='chathistory',
            name='question',
            field=models.TextField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='chathistory',
            name='answer',
            field=models.TextField(blank=True, db_index=True, null=True),
        ),

        # New fields for per-message chat tied to an Incident.
        migrations.AddField(
            model_name='chathistory',
            name='incident',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=models.deletion.CASCADE,
                related_name='chat_messages',
                to='Mapapi.incident',
            ),
        ),
        migrations.AddField(
            model_name='chathistory',
            name='user',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='chat_messages',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='chathistory',
            name='role',
            field=models.CharField(
                choices=[
                    ('user', 'User'),
                    ('assistant', 'Assistant'),
                    ('system', 'System'),
                ],
                default='user',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='chathistory',
            name='content',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='chathistory',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='chathistory',
            options={'ordering': ('created_at', 'id')},
        ),
    ]
