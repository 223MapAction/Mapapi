"""Authentification JWT par cookie httpOnly (avec repli Bearer).

Le frontend stocke le JWT dans un cookie **httpOnly** (illisible par JavaScript →
protégé contre le vol par XSS) au lieu du sessionStorage/localStorage. L'API
reste utilisable par le mobile via l'en-tête ``Authorization: Bearer`` (essayé
en premier). Quand l'authentification vient du cookie, on applique la protection
CSRF sur les méthodes non sûres (le cookie étant envoyé automatiquement par le
navigateur, c'est la contre-mesure indispensable).
"""
from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS', 'TRACE')


def _enforce_csrf(request):
    """Rejoue la vérification CSRF de Django pour une requête authentifiée par cookie."""
    def _dummy_get_response(_request):  # pragma: no cover - jamais appelé
        return None

    check = CSRFCheck(_dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f'CSRF Failed: {reason}')


class CookieJWTAuthentication(JWTAuthentication):
    """Bearer d'abord (mobile + transition), puis cookie httpOnly."""

    def authenticate(self, request):
        # 1. En-tête Authorization: Bearer — comportement historique inchangé.
        header_result = super().authenticate(request)
        if header_result is not None:
            return header_result

        # 2. Cookie httpOnly.
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
        if not raw_token:
            return None
        validated_token = self.get_validated_token(raw_token)
        # CSRF requis quand on s'appuie sur le cookie pour une méthode non sûre.
        if request.method not in SAFE_METHODS:
            _enforce_csrf(request)
        return self.get_user(validated_token), validated_token
