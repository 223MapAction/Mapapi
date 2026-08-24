"""Firebase Admin SDK initialization for push notifications (FCM).

Call :func:`init_firebase` once at app startup (see ``Mapapi.apps.MapapiConfig.ready``).
Safe to call more than once (e.g. autoreload) — reuses the existing app instead
of re-initializing.

The service account credentials can come from either:
- ``FCM_CREDENTIALS_PATH``: path to the JSON key file, for local/Docker setups
  where the file is mounted on disk.
- ``FCM_CREDENTIALS_JSON_BASE64``: the JSON key file, base64-encoded, for
  environments where only environment variables can be injected (Railway, AWS,
  GitHub Actions secrets → .env). Base64 avoids quoting/escaping issues that a
  raw JSON string (full of double quotes) would hit when piped through shell
  commands such as ``echo "VAR=$SECRET" >> .env``.
- ``FCM_CREDENTIALS_JSON``: the JSON key file content, raw, for platforms whose
  variable editor doesn't go through a shell (e.g. pasted directly into
  Railway's dashboard) and where base64 is just extra friction.

Checked in that order; the first one configured wins.
"""
import base64
import json
import logging

import firebase_admin
from firebase_admin import credentials
from django.conf import settings

logger = logging.getLogger(__name__)


def _load_credentials():
    credentials_path = getattr(settings, 'FCM_CREDENTIALS_PATH', None)
    if credentials_path:
        return credentials.Certificate(credentials_path)

    credentials_json_b64 = getattr(settings, 'FCM_CREDENTIALS_JSON_BASE64', None)
    if credentials_json_b64:
        info = json.loads(base64.b64decode(credentials_json_b64))
        return credentials.Certificate(info)

    credentials_json = getattr(settings, 'FCM_CREDENTIALS_JSON', None)
    if credentials_json:
        info = json.loads(credentials_json)
        return credentials.Certificate(info)

    return None


def init_firebase():
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    try:
        cred = _load_credentials()
    except Exception:  # JSON/base64 malformé, fichier illisible, etc. : ne jamais empêcher le démarrage
        logger.exception("Identifiants FCM invalides, notifications push désactivées")
        return

    if cred is None:
        logger.warning(
            "Aucun identifiant FCM configuré (FCM_CREDENTIALS_PATH / "
            "FCM_CREDENTIALS_JSON_BASE64 / FCM_CREDENTIALS_JSON) : les "
            "notifications push sont désactivées."
        )
        return

    firebase_admin.initialize_app(cred)
