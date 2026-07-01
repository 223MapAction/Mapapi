import os.path
import os
import sys
import logging
from pathlib import Path
from datetime import timedelta
# from dotenv import load_dotenv
import ast


# load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY")

# À changer quand on le mettra en production
DEBUG = True


# Split the comma-separated ALLOWED_HOSTS environment variable into a list
allowed_hosts_value = os.environ.get("ALLOWED_HOSTS", "localhost")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_value.split(",")]

# Add CSRF trusted origins for HTTPS. Inclut le frontend cross-site (cookies
# httpOnly + CSRF) : Railway, GitHub Pages, et le dev local (Vite :5173).
CSRF_TRUSTED_ORIGINS = [f"https://{host.strip()}" for host in allowed_hosts_value.split(",")]
CSRF_TRUSTED_ORIGINS += [
    "https://*.up.railway.app",
    "https://*.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]


# Application definition

INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'Mapapi',
    'crispy_forms',
    'crispy_bootstrap4',
    'allauth',
    'allauth.account',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    # 'allauth.socialaccount',
    # 'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.facebook',
    # 'allauth.socialaccount.providers.apple',
    # # 'allauth.socialaccount.providers.linkedin',
    # # 'allauth.socialaccount.providers.twitter_oauth2',
    # 'drf_spectacular',

]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"

CRISPY_TEMPLATE_PACK = "bootstrap4"

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

REST_FRAMEWORK = {
    # YOUR SETTINGS
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # JWT par cookie httpOnly (avec repli Bearer pour mobile/transition).
        'Mapapi.authentication.CookieJWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# --- Cookies d'authentification httpOnly (cf. Mapapi/authentication.py) ---
AUTH_COOKIE_ACCESS = 'access_token'
AUTH_COOKIE_REFRESH = 'refresh_token'

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=90),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": False,
    "SIGNING_KEY": 'django-insecure-4k+g*9g=6h&_8@s05ps!f)n!ivs4=yujv+rx(obnku=eyz3&jb',
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=5),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
    "TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",
    "TOKEN_VERIFY_SERIALIZER": "rest_framework_simplejwt.serializers.TokenVerifySerializer",
    "TOKEN_BLACKLIST_SERIALIZER": "rest_framework_simplejwt.serializers.TokenBlacklistSerializer",
    "SLIDING_TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainSlidingSerializer",
    "SLIDING_TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSlidingSerializer",
}
# Durées de vie des cookies = durées de vie des tokens.
AUTH_COOKIE_ACCESS_MAX_AGE = int(SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
AUTH_COOKIE_REFRESH_MAX_AGE = int(SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())

# Cookie CSRF : en prod le front et le back sont sur des domaines différents
# (cross-site) → le cookie csrftoken doit être SameSite=None; Secure pour être
# envoyé sur les requêtes cross-site. En local (http, same-site) on garde Lax.
# Piloté par env (COOKIE_SAMESITE=None, COOKIE_SECURE=True sur Railway).
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "Lax")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "False").lower() == "true"
CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
CSRF_COOKIE_SECURE = COOKIE_SECURE
# Le SPA lit le token CSRF dans le CORPS de la réponse (login / get_csrf_token),
# pas via document.cookie (illisible cross-site). On laisse toutefois le cookie
# lisible en JS pour le dev same-site.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE
SESSION_COOKIE_SECURE = COOKIE_SECURE
SPECTACULAR_SETTINGS = {
    'TITLE': 'Map Action API',
    'DESCRIPTION': (
        "API REST de la plateforme **Map Action** (gestion d'incidents "
        "environnementaux/humanitaires au Mali) qui sert le dashboard React et "
        "les clients mobile/IVR.\n\n"
        "## Authentification\n"
        "JWT **Bearer**. Connectez-vous via `POST /MapApi/login/` "
        "(`{email, password}` → `{access, refresh}`), cliquez sur **Authorize** "
        "en haut à droite et collez le token `access`. La connexion se fait par "
        "**email** (pas username). Token d'accès : 90 jours.\n\n"
        "## À savoir\n"
        "- **Préfixe** : toutes les routes sont sous `/MapApi/`.\n"
        "- **Slash final** : les routes sont insensibles au slash final "
        "(`/incident/1` ≡ `/incident/1/`).\n"
        "- **Ids** : ce sont des **UUID** (chaînes), pas des entiers.\n"
        "- **Beaucoup d'endpoints de lecture/référentiel sont publics** "
        "(pas d'auth) — voir le verrou sur chaque opération.\n"
        "- **Pagination** : les listes paginées renvoient "
        "`{count, next, previous, results}` (`?page=&page_size=`, défaut 100, "
        "max 1000) ; certaines listes renvoient un tableau brut.\n"
        "- **Uploads** : les endpoints avec fichiers "
        "(`photo, video, audio, attachment, proof_image, proof_video, logo`) "
        "exigent `multipart/form-data`.\n"
        "- **Messages** d'erreur/notification : en **français**."
    ),
    'VERSION': '1.0.0',
    'CONTACT': {'name': 'Map Action', 'url': 'https://github.com/223MapAction'},
    'LICENSE': {'name': 'Proprietary'},
    'SERVERS': [
        {'url': 'https://backend-production-0726b.up.railway.app', 'description': 'Production (Railway)'},
        {'url': 'http://localhost:8000', 'description': 'Dev local (daphne direct)'},
        {'url': 'http://localhost', 'description': 'Dev local (via nginx)'},
    ],
    'TAGS': [
        {'name': 'Authentification', 'description': 'Login, refresh, logout, inscription, mot de passe, vérification.'},
        {'name': 'Utilisateurs & Profil', 'description': 'Profil courant, gestion des utilisateurs, changement de mot de passe.'},
        {'name': 'Organisations & Membres', 'description': "Organisations, membres, création d'agents/staff."},
        {'name': 'Incidents', 'description': "CRUD, cycle de vie, listes filtrées (carte, dashboard), corbeille, stats."},
        {'name': 'Prise en charge & Collaboration', 'description': "Prise en charge, collaborations (émetteur/récepteur), accept/refus."},
        {'name': 'Tâches', 'description': "Tâches d'un incident : création, complétion (preuves), échec, confirmation."},
        {'name': 'Suggestions de partenaires', 'description': 'Suggestions de partenaires/organisations sur un incident.'},
        {'name': 'Rapports', 'description': "Rapports liés aux incidents."},
        {'name': 'Notifications', 'description': 'Notifications utilisateur (temps réel via WebSocket).'},
        {'name': 'Messages & Communauté', 'description': 'Messages, réponses, communautés.'},
        {'name': 'Zones', 'description': 'Zones géographiques (régions/cercles/communes).'},
        {'name': 'Catégories & Indicateurs', 'description': "Catégories d'incident et indicateurs."},
        {'name': 'Prédiction & IA', 'description': "Prédictions du modèle ML et assistant IA (chat) par incident."},
        {'name': 'Événements & Participation', 'description': 'Événements et participations citoyennes.'},
        {'name': 'Contacts & Élus', 'description': 'Contacts et élus locaux.'},
        {'name': 'Médias', 'description': "Images de fond / médias."},
        {'name': 'IVR (Téléphonie)', 'description': 'Flux vocal Twilio (signalement par téléphone).'},
        {'name': 'Référentiel & Statistiques', 'description': 'Endpoints de référence et statistiques (souvent publics).'},
    ],
    # Noms d'enum explicites — plusieurs jeux de choix s'appellent "role"/"status"
    # et drf-spectacular génère sinon des noms illisibles (Role8a8Enum…).
    'ENUM_NAME_OVERRIDES': {
        'OrgRoleEnum': 'Mapapi.models.ORG_ROLES',
        'CollaborationRoleEnum': 'Mapapi.models.COLLAB_ROLES',
        'ChatRoleEnum': 'Mapapi.models.CHAT_ROLES',
        'SuggestionRoleEnum': 'Mapapi.models.SUGGESTION_ROLES',
        'AssignmentStatusEnum': 'Mapapi.models.ASSIGNMENT_STATUSES',
        'OrgAssignmentStatusEnum': 'Mapapi.models.ORG_ASSIGNMENT_STATUSES',
        'SuggestionStatusEnum': 'Mapapi.models.SUGGESTION_STATUSES',
        'PartnerStatusEnum': 'Mapapi.models.PARTNER_STATUSES',
        'UserTypeEnum': 'Mapapi.models.USER_TYPES',
        'IncidentEtatEnum': 'Mapapi.models.ETAT_INCIDENT',
        'RapportEtatEnum': 'Mapapi.models.ETAT_RAPPORT',
        'TaskStateEnum': 'Mapapi.models.TASK_STATES',
        'SeverityEnum': 'Mapapi.models.SEVERITY_CHOICES',
    },
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,   # schémas requête/réponse distincts (lecture vs écriture)
    'SORT_OPERATIONS': False,          # garde l'ordre par tag/déclaration
    'SCHEMA_PATH_PREFIX': r'/MapApi',
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,  # garde le token entre les rechargements
        'displayRequestDuration': True,
        'filter': True,                # barre de recherche par tag/opération
        'docExpansion': 'none',
    },
    # UI Swagger/ReDoc en self-host : assets du paquet `drf-spectacular-sidecar`,
    # rassemblés par `collectstatic` (cf. Dockerfile.deploy) et servis par
    # WhiteNoise. Aucune dépendance à un CDN externe.
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise sert les fichiers statiques (UI Swagger/ReDoc) directement depuis
    # daphne en prod — il n'y a pas de nginx. Doit suivre SecurityMiddleware.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # Rend toutes les routes /MapApi/ insensibles au slash final (cf. middleware).
    'Mapapi.middleware.SlashInsensitiveMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'Mapapi.middleware.OrganisationFromSubdomainMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django_http_exceptions.middleware.ExceptionHandlerMiddleware',
    'django_http_exceptions.middleware.ThreadLocalRequestMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'template')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = 'backend.asgi.application'
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = "email"
SOCIALACCOUNT_QUERY_EMAIL = True
ACCOUNT_EMAIL_REQUIRED = True

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get("DB_HOST"),
        'NAME': os.environ.get("POSTGRES_DB"),
        'USER': os.environ.get("POSTGRES_USER"),
        'PASSWORD': os.environ.get("POSTGRES_PASSWORD"),
        'PORT': os.environ.get("PORT"),
        # La BDD est un pooler Supabase distant : ouvrir une connexion TLS à chaque
        # requête coûtait ~0,6 s (par requête, sur TOUS les endpoints). On réutilise
        # la connexion entre requêtes (60 s par défaut, ajustable via DB_CONN_MAX_AGE).
        'CONN_MAX_AGE': int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        # Revalide une connexion persistée avant réutilisation (le pooler peut la
        # fermer) et se reconnecte si elle est morte — évite les erreurs sur conn. obsolète.
        'CONN_HEALTH_CHECKS': True,
        # Pooler en mode « transaction » (pgbouncer, port 6543) : les curseurs côté
        # serveur ne survivent pas entre transactions → requis avec CONN_MAX_AGE.
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {
            # 'require' par défaut (Supabase) ; override en local/CI via DB_SSLMODE.
            'sslmode': os.environ.get('DB_SSLMODE', 'require'),
            # Schéma applicatif = public (best practice). Surcharge le search_path
            # par défaut du rôle Supabase (qui inclut 'extensions'). Override possible
            # via DB_SEARCH_PATH.
            'options': '-c search_path=' + os.environ.get('DB_SEARCH_PATH', 'public'),
        },
    },
}



# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators
TEST_RUNNER = 'Mapapi.test_runner.CoverageRunner'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, "static")
MEDIA_ROOT = os.path.join(BASE_DIR, 'uploads')
MEDIA_URL = '/uploads/'



# Default primary key field type

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth = JWT Bearer (le token, pas l'origine, fait foi). Aucune dépendance aux
# cookies cross-site → on autorise toutes les origines SANS credentials, ce qui
# laisse n'importe quel front (dashboard Railway, localhost:n'importe quel port,
# l'environnement de test du dev front, mobile) appeler l'API avec un Bearer.
# Note : '*' n'est permis par le navigateur QUE si les credentials sont désactivés.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost(:\d+)?$",
    r"^http://127\.0\.0\.1(:\d+)?$",
    r"^https://.*\.up\.railway\.app$",
    r"^https://.*\.github\.io$",
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    '*'
]

CORS_ALLOW_METHODS = [
    'GET',
    'PUT',
    'OPTIONS',
    'PATCH',
    'POST',
    '*'
]

CORS_ORIGIN_WHITELIST = [
    "http://localhost:80",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://139.144.63.238",
    "http://192.168.0.3",
    "http://192.168.0.3:8000",
    "http://192.168.1.26"

]


# Celery Configuration (broker/result configurable for deploys; defaults to the
# docker-compose 'redis-server' service for local).
# Channels (WebSockets temps réel) : couche Redis (réutilise le Redis Celery par
# défaut ; surchargeable via CHANNELS_REDIS_URL).
CHANNELS_REDIS_URL = os.environ.get(
    'CHANNELS_REDIS_URL',
    os.environ.get('CELERY_BROKER_URL', 'redis://redis-server:6379/0'),
)
CHANNEL_LAYERS = {
    'default': {
        # Couche pub/sub Redis : fan-out fiable des broadcasts entre processus
        # (HTTP qui émet via group_send ↔ Daphne qui relaie au WebSocket). L'ancienne
        # RedisChannelLayer (listes + BZPOPMIN bloquant) ne délivrait pas les messages
        # cross-process et se fermait en 1011 (aggravé par redis-py >= 5.1).
        'BACKEND': 'channels_redis.pubsub.RedisPubSubChannelLayer',
        'CONFIG': {'hosts': [CHANNELS_REDIS_URL]},
    },
}
# Origines autorisées pour les WebSockets. L'anti-hijacking par origine ne protège
# que l'auth par cookie ; ici le WS est authentifié par ?token=<JWT> (le token fait
# foi), donc on autorise toutes les origines par défaut — un front cross-site ne
# peut rien faire sans le token. Surchargeable via CHANNELS_ALLOWED_ORIGINS.
WS_ALLOWED_ORIGINS = os.environ.get(
    'CHANNELS_ALLOWED_ORIGINS',
    '*',
).split(',')

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis-server:6379/0')
CELERY_RESULT_BACKEND = os.environ.get(
    'CELERY_RESULT_BACKEND',
    os.environ.get('CELERY_BROKER_URL', 'redis://redis-server:6379/0'),
)
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# Phase 4 — mécanismes temporels du cycle de vie de l'incident (Celery Beat).
# Validation tacite 72 h (D1) + anti-gel (T3) : horaires. Purge corbeille 30 j (D10) : quotidien.
CELERY_BEAT_SCHEDULE = {
    'auto-validate-overdue-resolutions': {
        'task': 'Mapapi.tasks.auto_validate_overdue_resolutions',
        'schedule': timedelta(hours=1),
    },
    'revert-stale-taken-incidents': {
        'task': 'Mapapi.tasks.revert_stale_taken_incidents',
        'schedule': timedelta(hours=1),
    },
    'purge-expired-trash': {
        'task': 'Mapapi.tasks.purge_expired_trash',
        'schedule': timedelta(days=1),
    },
    # Acceptation tacite des assignations Super Admin → organisation à 72 h (D4) : horaire.
    'auto-accept-overdue-assignments': {
        'task': 'Mapapi.tasks.auto_accept_overdue_assignments',
        'schedule': timedelta(hours=1),
    },
}

# Django Q Configuration
Q_CLUSTER = {
    'name': 'backend',
    'workers': 8,
    'recycle': 500,
    'timeout': 60,
    'compress': True,
    'save_limit': 250,
    'queue_limit': 500,
    'cpu_affinity': 1,
    'label': 'Django Q',
    'redis': {
        'host': 'redis-server',
        'port': 6379,
        'db': 0,
        'password': None,
        'socket_timeout': None,
        'charset': 'utf-8',
        'errors': 'strict',
        'unix_socket_path': None
    }
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'httpx': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'httpcore': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'httpcore.http2': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'httpcore.connection': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'hpack': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'h2': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}


AUTH_USER_MODEL = 'Mapapi.User'
# Config email entièrement pilotée par l'env (valeurs par défaut = config actuelle,
# donc aucun changement de comportement si les variables ne sont pas définies).
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 2525))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Map Action <contact@map-action.com>")

# Supabase storage configuration
USE_SUPABASE_STORAGE = os.environ.get('USE_SUPABASE_STORAGE', 'False').lower() in ('true', '1', 't')

# Twilio configuration for IVR
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

# SMS OTP : envoyé via Twilio (cf. Mapapi/views/user.py send_sms). L'ancienne
# intégration Orange Mali a été retirée (alignement avec l'upstream « orange to twilio »).

# Model-deploy service (remote AI analysis pipeline).
# NB: the service exposes /analyze, /analyze/upload and /chat — there is NO
# "/api1" prefix. The photo-upload task posts multipart → /analyze/upload.
MODEL_DEPLOY_ANALYZE_URL = os.environ.get(
    'MODEL_DEPLOY_ANALYZE_URL',
    'http://localhost:8001/analyze/upload',
)
MODEL_DEPLOY_TIMEOUT = int(os.environ.get('MODEL_DEPLOY_TIMEOUT', 180))
MODEL_DEPLOY_CHAT_URL = os.environ.get(
    'MODEL_DEPLOY_CHAT_URL',
    'http://localhost:8001/chat',
)
MODEL_DEPLOY_CHAT_TIMEOUT = int(os.environ.get('MODEL_DEPLOY_CHAT_TIMEOUT', 120))