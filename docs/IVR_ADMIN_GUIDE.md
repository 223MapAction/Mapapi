# Guide d'Administration du Système IVR

## Accès aux données IVR

### Via l'API REST

#### Lister tous les appels IVR
```bash
curl -X GET https://votre-domaine.com/MapApi/ivr/calls/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

#### Voir les détails d'un appel spécifique
```bash
curl -X GET https://votre-domaine.com/MapApi/ivr/calls/1/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Via Django Admin

1. Ajoutez les modèles IVR à votre `admin.py` :

```python
from django.contrib import admin
from .models import IVRCall, IVRInteraction

@admin.register(IVRCall)
class IVRCallAdmin(admin.ModelAdmin):
    list_display = ['call_sid', 'phone_number', 'status', 'zone_selected', 'created_at']
    list_filter = ['status', 'created_at', 'zone_selected']
    search_fields = ['call_sid', 'phone_number']
    readonly_fields = ['call_sid', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Informations d\'appel', {
            'fields': ('call_sid', 'phone_number', 'status')
        }),
        ('Données collectées', {
            'fields': ('zone_selected', 'category_selected', 'description_audio_url', 'description_audio_duration')
        }),
        ('Résultat', {
            'fields': ('incident_created', 'user')
        }),
        ('Horodatage', {
            'fields': ('created_at', 'updated_at')
        }),
    )

@admin.register(IVRInteraction)
class IVRInteractionAdmin(admin.ModelAdmin):
    list_display = ['ivr_call', 'step', 'user_input', 'timestamp']
    list_filter = ['step', 'timestamp']
    search_fields = ['ivr_call__call_sid']
    readonly_fields = ['timestamp']
```

## Monitoring et Statistiques

### Requêtes SQL utiles

#### Nombre d'appels par jour
```sql
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_calls,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_calls
FROM Mapapi_ivrcall
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

#### Zones les plus signalées
```sql
SELECT 
    zone_selected,
    COUNT(*) as count
FROM Mapapi_ivrcall
WHERE zone_selected IS NOT NULL
GROUP BY zone_selected
ORDER BY count DESC;
```

#### Catégories les plus signalées
```sql
SELECT 
    c.name,
    COUNT(*) as count
FROM Mapapi_ivrcall ivr
JOIN Mapapi_category c ON ivr.category_selected_id = c.id
WHERE ivr.category_selected_id IS NOT NULL
GROUP BY c.name
ORDER BY count DESC;
```

#### Durée moyenne des enregistrements
```sql
SELECT 
    AVG(description_audio_duration) as avg_duration,
    MIN(description_audio_duration) as min_duration,
    MAX(description_audio_duration) as max_duration
FROM Mapapi_ivrcall
WHERE description_audio_duration IS NOT NULL;
```

## Gestion des enregistrements audio

### Télécharger les enregistrements Twilio

Les enregistrements sont stockés sur Twilio. Pour les télécharger :

```python
from twilio.rest import Client
from django.conf import settings
import requests

def download_recording(recording_url, save_path):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    
    # Ajouter .mp3 pour obtenir le format audio
    audio_url = recording_url + '.mp3'
    
    # Télécharger avec authentification
    response = requests.get(
        audio_url,
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    )
    
    if response.status_code == 200:
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    return False
```

### Script de sauvegarde des enregistrements

```python
# management/commands/backup_ivr_recordings.py
from django.core.management.base import BaseCommand
from Mapapi.models import IVRCall
import os
import requests
from django.conf import settings

class Command(BaseCommand):
    help = 'Backup IVR recordings from Twilio'

    def handle(self, *args, **options):
        calls = IVRCall.objects.filter(
            description_audio_url__isnull=False
        )
        
        backup_dir = 'ivr_backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        for call in calls:
            filename = f"{call.call_sid}.mp3"
            filepath = os.path.join(backup_dir, filename)
            
            if os.path.exists(filepath):
                self.stdout.write(f"Skipping {filename} (already exists)")
                continue
            
            audio_url = call.description_audio_url + '.mp3'
            response = requests.get(
                audio_url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            )
            
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                self.stdout.write(
                    self.style.SUCCESS(f"Downloaded {filename}")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"Failed to download {filename}")
                )
```

Exécuter : `python manage.py backup_ivr_recordings`

## Résolution de problèmes

### L'appel se termine immédiatement

**Causes possibles :**
- URL du webhook incorrecte dans Twilio
- Serveur non accessible publiquement
- Erreur dans le code du webhook

**Solution :**
1. Vérifier les logs Twilio : Console > Monitor > Logs > Errors
2. Vérifier que l'URL est accessible : `curl https://votre-domaine.com/MapApi/ivr/webhook/`
3. Vérifier les logs Django

### Les enregistrements ne sont pas sauvegardés

**Causes possibles :**
- Callback URL incorrecte
- Problème de permissions

**Solution :**
1. Vérifier que `/MapApi/ivr/recording-status/` est accessible
2. Vérifier les logs Twilio pour les callbacks
3. Vérifier les logs Django

### Les incidents ne sont pas créés

**Causes possibles :**
- Erreur dans la création de l'utilisateur
- Données manquantes (zone, catégorie)

**Solution :**
1. Vérifier les logs Django
2. Vérifier que les zones et catégories existent dans la base de données
3. Vérifier le modèle `IVRCall` pour voir les données collectées

### Logs Django

Ajouter plus de logging :

```python
import logging
logger = logging.getLogger(__name__)

# Dans vos views
logger.info(f"IVR Call received: {call_sid}")
logger.error(f"Error creating incident: {str(e)}")
```

## Maintenance

### Nettoyage des anciens appels

```python
# management/commands/cleanup_old_ivr_calls.py
from django.core.management.base import BaseCommand
from Mapapi.models import IVRCall
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Delete IVR calls older than 90 days'

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - timedelta(days=90)
        old_calls = IVRCall.objects.filter(created_at__lt=cutoff_date)
        count = old_calls.count()
        old_calls.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} old IVR calls")
        )
```

### Mise à jour des zones/catégories

Si vous ajoutez plus de 9 zones ou catégories, le système IVR ne pourra afficher que les 9 premières. Pour gérer cela :

1. **Option 1** : Créer des sous-menus
2. **Option 2** : Filtrer par région géographique
3. **Option 3** : Utiliser la reconnaissance vocale (nécessite Twilio Autopilot)

## Tableau de bord personnalisé

Créez une vue pour visualiser les statistiques IVR :

```python
from django.db.models import Count, Avg
from rest_framework.views import APIView
from rest_framework.response import Response

class IVRStatsView(APIView):
    def get(self, request):
        total_calls = IVRCall.objects.count()
        completed_calls = IVRCall.objects.filter(status='completed').count()
        
        zones_stats = IVRCall.objects.values('zone_selected').annotate(
            count=Count('id')
        ).order_by('-count')
        
        avg_duration = IVRCall.objects.aggregate(
            avg=Avg('description_audio_duration')
        )['avg']
        
        return Response({
            'total_calls': total_calls,
            'completed_calls': completed_calls,
            'completion_rate': (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            'zones_stats': zones_stats,
            'avg_recording_duration': avg_duration
        })
```

## Alertes et notifications

Configurez des alertes pour être notifié des nouveaux signalements :

```python
# Dans ProcessRecordingView, après la création de l'incident
from django.core.mail import send_mail

send_mail(
    subject=f'Nouveau signalement IVR - {ivr_call.zone_selected}',
    message=f'Un incident a été signalé par téléphone.\n'
            f'Zone: {ivr_call.zone_selected}\n'
            f'Catégorie: {ivr_call.category_selected.name if ivr_call.category_selected else "N/A"}\n'
            f'Téléphone: {ivr_call.phone_number}\n'
            f'Incident ID: {incident.id}',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['admin@mapaction.com'],
    fail_silently=True,
)
```
