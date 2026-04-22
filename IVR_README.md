# Système IVR pour Map Action

## 🎯 Objectif

Permettre aux citoyens qui n'ont pas accès à un smartphone de signaler des incidents via un simple appel téléphonique, en utilisant les touches de leur téléphone (DTMF).

## ✅ Fonctionnalités implémentées

- ✅ **Menu vocal interactif en français** avec voix Polly.Celine
- ✅ **Sélection de zone** via touches numériques (1-9)
- ✅ **Sélection de catégorie** via touches numériques (1-9)
- ✅ **Enregistrement audio** de la description de l'incident (max 120 secondes)
- ✅ **Création automatique d'utilisateur** basé sur le numéro de téléphone
- ✅ **Création automatique d'incident** avec toutes les données collectées
- ✅ **Stockage des interactions** pour analyse et suivi
- ✅ **API REST** pour consulter les appels IVR
- ✅ **Interface d'administration Django** pour gérer les appels

## 📋 Fichiers créés

### Modèles
- `Mapapi/models.py` - Ajout des modèles `IVRCall` et `IVRInteraction`

### Views
- `Mapapi/ivr_views.py` - Toutes les vues pour gérer le flux IVR :
  - `TwilioIVRWebhook` - Point d'entrée initial
  - `SelectZoneView` - Gestion de la sélection de zone
  - `SelectCategoryView` - Gestion de la sélection de catégorie
  - `RecordDescriptionView` - Démarrage de l'enregistrement
  - `ProcessRecordingView` - Traitement et création de l'incident
  - `RecordingStatusView` - Callback pour le statut d'enregistrement
  - `IVRCallListView` - API pour lister les appels
  - `IVRCallDetailView` - API pour voir les détails d'un appel

### URLs
- `Mapapi/urls.py` - Routes ajoutées :
  - `/MapApi/ivr/webhook/` - Webhook principal Twilio
  - `/MapApi/ivr/select-zone/` - Sélection de zone
  - `/MapApi/ivr/select-category/` - Sélection de catégorie
  - `/MapApi/ivr/record-description/` - Enregistrement
  - `/MapApi/ivr/process-recording/` - Traitement
  - `/MapApi/ivr/recording-status/` - Statut
  - `/MapApi/ivr/calls/` - Liste des appels (API)
  - `/MapApi/ivr/calls/<id>/` - Détails d'un appel (API)

### Configuration
- `backend/settings.py` - Variables Twilio ajoutées

### Administration
- `Mapapi/admin.py` - Interface admin pour `IVRCall` et `IVRInteraction`

### Documentation
- `docs/IVR_SETUP.md` - Guide complet de configuration
- `docs/IVR_ADMIN_GUIDE.md` - Guide d'administration
- `docs/IVR_EXAMPLE_ENV.md` - Configuration des variables d'environnement

### Tests
- `Mapapi/management/commands/test_ivr_flow.py` - Script de test du flux IVR

## 🚀 Démarrage rapide

### 1. Installer les dépendances

Le package `twilio==9.0.3` est déjà dans `requirements.txt`.

### 2. Configurer les variables d'environnement

Ajoutez dans votre `.env` :

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+237690000000
```

### 3. Exécuter les migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Tester localement avec ngrok

```bash
# Terminal 1 : Démarrer Django
python manage.py runserver

# Terminal 2 : Exposer avec ngrok
ngrok http 8000
```

Copiez l'URL ngrok (ex: `https://abc123.ngrok.io`) et configurez-la dans Twilio.

### 5. Configurer Twilio

1. Allez sur https://console.twilio.com
2. Phone Numbers > Manage > Active Numbers
3. Cliquez sur votre numéro
4. Dans "Voice & Fax" :
   - **A CALL COMES IN** : Webhook
   - **URL** : `https://votre-domaine.com/MapApi/ivr/webhook/`
   - **HTTP** : POST

### 6. Tester

Appelez votre numéro Twilio et suivez les instructions !

## 📊 Flux de l'appel

```
┌─────────────────────────────────────────┐
│  Utilisateur appelle le numéro Twilio  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Message d'accueil                      │
│  "Bienvenue au système..."              │
│  1 = Signaler incident                  │
│  2 = Parler à un opérateur              │
└──────────────┬──────────────────────────┘
               │ (appuie sur 1)
               ▼
┌─────────────────────────────────────────┐
│  Sélection de zone                      │
│  "Pour Douala, appuyez sur 1..."        │
└──────────────┬──────────────────────────┘
               │ (appuie sur 1-9)
               ▼
┌─────────────────────────────────────────┐
│  Sélection de catégorie                 │
│  "Pour Déchets, appuyez sur 1..."       │
└──────────────┬──────────────────────────┘
               │ (appuie sur 1-9)
               ▼
┌─────────────────────────────────────────┐
│  Enregistrement audio                   │
│  "Décrivez l'incident après le bip..."  │
│  (max 120 secondes)                     │
└──────────────┬──────────────────────────┘
               │ (appuie sur #)
               ▼
┌─────────────────────────────────────────┐
│  Traitement et création                 │
│  - Création utilisateur (si nouveau)    │
│  - Création incident                    │
│  - Sauvegarde audio                     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Confirmation                           │
│  "Merci, votre incident a été           │
│   enregistré. Au revoir."               │
└─────────────────────────────────────────┘
```

## 🔍 Consultation des données

### Via l'API

```bash
# Liste de tous les appels
curl https://votre-domaine.com/MapApi/ivr/calls/

# Détails d'un appel spécifique
curl https://votre-domaine.com/MapApi/ivr/calls/1/
```

### Via Django Admin

1. Allez sur `/admin/`
2. Section "Mapapi"
3. Consultez "IVR Calls" et "IVR Interactions"

## 🧪 Tests

Testez le flux complet sans appeler :

```bash
python manage.py test_ivr_flow
```

Ce script simule un appel complet et vérifie que :
- L'appel IVR est créé
- Les interactions sont enregistrées
- La zone et catégorie sont sélectionnées
- L'incident est créé
- L'utilisateur est créé

## 📝 Modèles de données

### IVRCall
Chaque appel crée un enregistrement `IVRCall` avec :
- Identifiant Twilio (`call_sid`)
- Numéro de téléphone
- Statut de l'appel
- Zone sélectionnée
- Catégorie sélectionnée
- URL de l'enregistrement audio
- Incident créé (référence)
- Utilisateur (référence)

### IVRInteraction
Chaque action de l'utilisateur crée une `IVRInteraction` :
- Étape du flux (`main_menu`, `zone_selection`, etc.)
- Touche appuyée
- URL d'enregistrement (si applicable)
- Horodatage

## 💡 Avantages

1. **Accessibilité** : Fonctionne avec n'importe quel téléphone
2. **Pas de connexion Internet** : Juste un appel téléphonique
3. **Facile à utiliser** : Menu vocal guidé
4. **Traçabilité** : Toutes les interactions sont enregistrées
5. **Audio conservé** : La description vocale est sauvegardée
6. **Automatique** : Création d'incident sans intervention manuelle

## 💰 Coûts estimés (Twilio)

Pour 100 appels/mois au Cameroun :
- Numéro : ~$5/mois
- Appels (2 min/appel) : ~$1.70/mois
- Enregistrements (30s/appel) : ~$0.13/mois
- **Total : ~$7/mois**

## 📚 Documentation complète

- `docs/IVR_SETUP.md` - Configuration détaillée
- `docs/IVR_ADMIN_GUIDE.md` - Administration et monitoring
- `docs/IVR_EXAMPLE_ENV.md` - Variables d'environnement

## 🔒 Sécurité

- Les webhooks Twilio sont protégés par CSRF exempt (requis par Twilio)
- Validation de signature Twilio recommandée en production
- HTTPS requis en production
- Les enregistrements sont stockés sur Twilio (sécurisé)

## 🎉 Prêt à utiliser !

Le système est maintenant opérationnel. Il suffit de :
1. Configurer vos identifiants Twilio
2. Exécuter les migrations
3. Configurer le webhook dans Twilio
4. Commencer à recevoir des signalements par téléphone !

---

**Questions ou problèmes ?** Consultez `docs/IVR_SETUP.md` pour plus de détails.
