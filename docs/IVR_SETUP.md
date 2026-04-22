# Configuration du Système IVR avec Twilio

## Vue d'ensemble

Ce système permet aux utilisateurs de signaler des incidents par téléphone sans avoir besoin d'un smartphone ou d'une connexion Internet. Le système utilise Twilio pour gérer les appels téléphoniques et enregistrer les informations via un système IVR (Interactive Voice Response).

## Fonctionnalités

- ✅ Signalement d'incidents par téléphone classique (avec boutons)
- ✅ Menu vocal interactif en français
- ✅ Sélection de zone par touches DTMF
- ✅ Sélection de catégorie d'incident
- ✅ Enregistrement audio de la description de l'incident
- ✅ Création automatique d'un utilisateur basé sur le numéro de téléphone
- ✅ Stockage de toutes les interactions IVR
- ✅ Création automatique d'incident avec l'audio attaché

## Configuration

### 1. Variables d'environnement

Ajoutez les variables suivantes dans votre fichier `.env` :

```env
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=your_twilio_phone_number
```

### 2. Configuration Twilio

1. **Créer un compte Twilio** : https://www.twilio.com/try-twilio
2. **Acheter un numéro de téléphone** avec capacités vocales
3. **Configurer le webhook** :
   - Allez dans Phone Numbers > Manage > Active Numbers
   - Sélectionnez votre numéro
   - Dans "Voice & Fax", configurez :
     - **A CALL COMES IN** : Webhook
     - **URL** : `https://votre-domaine.com/MapApi/ivr/webhook/`
     - **HTTP** : POST

### 3. Migration de la base de données

Exécutez les migrations pour créer les nouvelles tables :

```bash
python manage.py makemigrations
python manage.py migrate
```

## Flux IVR

### Étape 1 : Accueil
L'utilisateur appelle le numéro Twilio et entend :
> "Bienvenue au système de signalement d'incidents de Map Action. Pour signaler un incident, appuyez sur 1. Pour parler à un opérateur, appuyez sur 2."

### Étape 2 : Sélection de la zone
Si l'utilisateur appuie sur 1 :
> "Veuillez sélectionner votre zone. Pour [Zone 1], appuyez sur 1. Pour [Zone 2], appuyez sur 2..."

### Étape 3 : Sélection de la catégorie
Après avoir sélectionné la zone :
> "Veuillez sélectionner la catégorie de l'incident. Pour [Catégorie 1], appuyez sur 1. Pour [Catégorie 2], appuyez sur 2..."

### Étape 4 : Enregistrement de la description
Après avoir sélectionné la catégorie :
> "Veuillez décrire l'incident après le bip. Appuyez sur dièse lorsque vous avez terminé."

L'utilisateur enregistre sa description (max 120 secondes).

### Étape 5 : Confirmation
> "Merci pour votre signalement. Votre incident a été enregistré avec succès. Au revoir."

## Modèles de données

### IVRCall
Stocke les informations principales de chaque appel :
- `call_sid` : Identifiant unique Twilio
- `phone_number` : Numéro de téléphone de l'appelant
- `status` : Statut de l'appel (initiated, completed, etc.)
- `zone_selected` : Zone sélectionnée
- `category_selected` : Catégorie sélectionnée
- `description_audio_url` : URL de l'enregistrement audio
- `description_audio_duration` : Durée de l'enregistrement
- `incident_created` : Référence à l'incident créé
- `user` : Utilisateur créé/trouvé

### IVRInteraction
Stocke chaque interaction de l'utilisateur :
- `ivr_call` : Référence à l'appel IVR
- `step` : Étape du flux (main_menu, zone_selection, etc.)
- `user_input` : Touche appuyée par l'utilisateur
- `recording_url` : URL de l'enregistrement (si applicable)
- `recording_duration` : Durée de l'enregistrement
- `timestamp` : Horodatage de l'interaction

## Endpoints API

### Webhooks Twilio (utilisés par Twilio)
- `POST /MapApi/ivr/webhook/` - Point d'entrée initial
- `POST /MapApi/ivr/select-zone/` - Sélection de zone
- `POST /MapApi/ivr/select-category/` - Sélection de catégorie
- `POST /MapApi/ivr/record-description/` - Enregistrement de description
- `POST /MapApi/ivr/process-recording/` - Traitement de l'enregistrement
- `POST /MapApi/ivr/recording-status/` - Statut de l'enregistrement

### API de consultation
- `GET /MapApi/ivr/calls/` - Liste de tous les appels IVR
- `GET /MapApi/ivr/calls/<call_id>/` - Détails d'un appel spécifique avec toutes ses interactions

## Test en local avec ngrok

Pour tester localement, utilisez ngrok pour exposer votre serveur local :

```bash
# Installer ngrok
brew install ngrok  # macOS
# ou télécharger depuis https://ngrok.com/

# Exposer votre serveur local
ngrok http 8000

# Copier l'URL HTTPS générée (ex: https://abc123.ngrok.io)
# Configurer dans Twilio : https://abc123.ngrok.io/MapApi/ivr/webhook/
```

## Exemple de réponse API

### GET /MapApi/ivr/calls/
```json
[
  {
    "id": 1,
    "call_sid": "CA1234567890abcdef",
    "phone_number": "+237690000000",
    "status": "completed",
    "zone_selected": "Douala",
    "category_selected": "Déchets",
    "description_audio_url": "https://api.twilio.com/recordings/RE123...",
    "description_audio_duration": 45,
    "incident_id": 123,
    "created_at": "2024-02-06T12:30:00Z",
    "updated_at": "2024-02-06T12:32:00Z"
  }
]
```

### GET /MapApi/ivr/calls/1/
```json
{
  "id": 1,
  "call_sid": "CA1234567890abcdef",
  "phone_number": "+237690000000",
  "status": "completed",
  "zone_selected": "Douala",
  "category_selected": "Déchets",
  "description_audio_url": "https://api.twilio.com/recordings/RE123...",
  "description_audio_duration": 45,
  "incident_id": 123,
  "created_at": "2024-02-06T12:30:00Z",
  "updated_at": "2024-02-06T12:32:00Z",
  "interactions": [
    {
      "step": "main_menu",
      "user_input": "1",
      "recording_url": null,
      "recording_duration": null,
      "timestamp": "2024-02-06T12:30:15Z"
    },
    {
      "step": "zone_selection",
      "user_input": "2",
      "recording_url": null,
      "recording_duration": null,
      "timestamp": "2024-02-06T12:30:30Z"
    },
    {
      "step": "category_selection",
      "user_input": "3",
      "recording_url": null,
      "recording_duration": null,
      "timestamp": "2024-02-06T12:30:45Z"
    },
    {
      "step": "description_recording",
      "user_input": null,
      "recording_url": "https://api.twilio.com/recordings/RE123...",
      "recording_duration": 45,
      "timestamp": "2024-02-06T12:31:30Z"
    }
  ]
}
```

## Sécurité

### Validation des requêtes Twilio
Pour valider que les requêtes proviennent bien de Twilio, vous pouvez ajouter la validation de signature :

```python
from twilio.request_validator import RequestValidator

def validate_twilio_request(request):
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    url = request.build_absolute_uri()
    signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')
    return validator.validate(url, request.POST, signature)
```

## Limitations

- Maximum 9 zones affichables dans le menu (limitation DTMF)
- Maximum 9 catégories affichables dans le menu
- Durée maximale d'enregistrement : 120 secondes
- Les enregistrements sont hébergés par Twilio

## Coûts Twilio (approximatifs)

- Numéro de téléphone : ~1-5 USD/mois
- Appel entrant : ~0.0085 USD/minute
- Enregistrement : ~0.0025 USD/minute

## Améliorations futures possibles

- [ ] Support de plusieurs langues
- [ ] Transcription automatique des enregistrements audio
- [ ] Envoi de SMS de confirmation
- [ ] Géolocalisation basée sur le numéro de téléphone
- [ ] Menu dynamique basé sur la localisation
- [ ] Support de plus de 9 zones/catégories avec navigation multi-niveaux
- [ ] Notification aux administrateurs lors d'un nouveau signalement
- [ ] Rappel automatique en cas d'appel interrompu

## Support

Pour toute question ou problème, consultez :
- Documentation Twilio : https://www.twilio.com/docs/voice
- TwiML Voice : https://www.twilio.com/docs/voice/twiml
