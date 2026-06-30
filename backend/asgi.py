"""
ASGI config for backend project.

Route HTTP (Django) ET WebSocket (Channels). Le WS est authentifié par le JWT
(cookie httpOnly ou ?token=) via JWTCookieAuthMiddleware.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# L'app HTTP Django doit être initialisée avant d'importer les consumers
# (qui touchent aux modèles).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from Mapapi.routing import websocket_urlpatterns  # noqa: E402
from Mapapi.ws_auth import JWTCookieAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    # Origine validée (anti-hijacking cross-site) PUIS auth JWT (cookie/?token=).
    'websocket': OriginValidator(
        JWTCookieAuthMiddleware(URLRouter(websocket_urlpatterns)),
        settings.WS_ALLOWED_ORIGINS,
    ),
})
