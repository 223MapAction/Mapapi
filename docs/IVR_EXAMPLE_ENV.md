# Configuration des variables d'environnement pour IVR

## Fichier .env

Ajoutez ces lignes à votre fichier `.env` :

```env
# Configuration Twilio pour IVR
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+237690000000
```

## Obtenir vos identifiants Twilio

### 1. Créer un compte Twilio

1. Allez sur https://www.twilio.com/try-twilio
2. Créez un compte gratuit (vous recevrez des crédits de test)
3. Vérifiez votre email et numéro de téléphone

### 2. Trouver vos identifiants

Une fois connecté à la console Twilio :

1. **Account SID** et **Auth Token** :
   - Disponibles sur le tableau de bord principal
   - Console > Account > API credentials
   - Copiez le `Account SID` et le `Auth Token`

2. **Numéro de téléphone** :
   - Allez dans Phone Numbers > Manage > Buy a number
   - Sélectionnez votre pays (Cameroun pour +237)
   - Filtrez par "Voice" capabilities
   - Achetez un numéro (environ $1-5/mois)

### 3. Configurer le webhook du numéro

1. Allez dans Phone Numbers > Manage > Active Numbers
2. Cliquez sur votre numéro
3. Dans la section "Voice & Fax" :
   - **Configure with** : Webhooks, TwiML Bins, Functions, Studio, or Proxy
   - **A CALL COMES IN** : Webhook
   - **URL** : `https://votre-domaine.com/MapApi/ivr/webhook/`
   - **HTTP** : POST
4. Sauvegardez

## Test en développement local

Pour tester localement, vous devez exposer votre serveur local à Internet :

### Utiliser ngrok

```bash
# Installer ngrok
# macOS
brew install ngrok

# Linux
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin

# Créer un compte sur https://ngrok.com et obtenir votre authtoken
ngrok config add-authtoken YOUR_AUTHTOKEN

# Démarrer votre serveur Django
python manage.py runserver

# Dans un autre terminal, exposer le port 8000
ngrok http 8000
```

Vous obtiendrez une URL comme : `https://abc123.ngrok.io`

Configurez cette URL dans Twilio :
- Webhook URL : `https://abc123.ngrok.io/MapApi/ivr/webhook/`

### Alternative : localtunnel

```bash
# Installer localtunnel
npm install -g localtunnel

# Exposer votre serveur
lt --port 8000
```

## Vérification de la configuration

### Test 1 : Vérifier que le webhook est accessible

```bash
curl -X POST https://votre-domaine.com/MapApi/ivr/webhook/ \
  -d "CallSid=TEST123" \
  -d "From=+237690000000" \
  -d "CallStatus=ringing"
```

Vous devriez recevoir une réponse XML TwiML.

### Test 2 : Appeler le numéro Twilio

1. Appelez le numéro Twilio depuis votre téléphone
2. Vous devriez entendre le message d'accueil en français
3. Suivez les instructions du menu IVR

### Test 3 : Vérifier les logs

```bash
# Logs Django
tail -f logs/django.log

# Logs Twilio
# Allez dans Console > Monitor > Logs > Errors
```

## Sécurité en production

### 1. Valider les requêtes Twilio

Ajoutez cette validation dans vos views :

```python
from twilio.request_validator import RequestValidator
from django.conf import settings

def validate_twilio_request(request):
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    url = request.build_absolute_uri()
    signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')
    
    post_vars = {}
    for key, value in request.POST.items():
        post_vars[key] = value
    
    return validator.validate(url, post_vars, signature)
```

### 2. Utiliser HTTPS

Twilio requiert HTTPS pour les webhooks en production. Assurez-vous que :
- Votre serveur utilise un certificat SSL valide
- Les URLs de webhook utilisent `https://`

### 3. Restreindre l'accès aux endpoints IVR

Les endpoints IVR ne nécessitent pas d'authentification JWT car ils sont appelés par Twilio. Cependant, validez toujours la signature Twilio.

## Coûts estimés

### Compte gratuit Twilio
- $15.50 de crédits gratuits
- Parfait pour les tests

### Coûts en production (Cameroun)
- **Numéro de téléphone** : ~$1-5 USD/mois
- **Appel entrant** : ~$0.0085 USD/minute
- **Enregistrement** : ~$0.0025 USD/minute

**Exemple de calcul :**
- 100 appels/mois
- Durée moyenne : 2 minutes/appel
- Enregistrement moyen : 30 secondes

Coût mensuel :
- Numéro : $5
- Appels : 100 × 2 × $0.0085 = $1.70
- Enregistrements : 100 × 0.5 × $0.0025 = $0.125
- **Total : ~$6.83/mois**

## Dépannage

### Erreur : "Unable to create record: Webhook Error - 11200"

**Cause** : L'URL du webhook n'est pas accessible

**Solution** :
- Vérifiez que votre serveur est en ligne
- Vérifiez que l'URL est correcte
- Testez l'URL avec curl

### Erreur : "TwiML did not contain a Response"

**Cause** : Le webhook ne retourne pas de XML valide

**Solution** :
- Vérifiez que vous retournez `HttpResponse(str(response), content_type='text/xml')`
- Vérifiez les logs Django pour les erreurs

### Les enregistrements ne sont pas sauvegardés

**Cause** : Le callback de statut n'est pas appelé

**Solution** :
- Vérifiez que `/MapApi/ivr/recording-status/` est accessible
- Vérifiez les logs Twilio pour les erreurs de callback

### Le menu vocal est en anglais

**Cause** : La voix ou la langue n'est pas configurée correctement

**Solution** :
- Vérifiez que `language='fr-FR'` et `voice='Polly.Celine'` sont définis
- Autres voix françaises disponibles : 'Polly.Mathieu', 'Polly.Lea'

## Support

- Documentation Twilio : https://www.twilio.com/docs/voice
- Support Twilio : https://support.twilio.com
- Forum Twilio : https://www.twilio.com/community
