"""drf-spectacular extensions & hooks for the Map Action OpenAPI schema.

Imported at startup (from ``Mapapi/urls.py``) so the extensions below register
themselves with drf-spectacular.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CookieJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Expose le JWT Bearer (et le cookie httpOnly) dans le schéma OpenAPI.

    Sans cette extension drf-spectacular ne reconnaît pas la classe custom
    ``CookieJWTAuthentication`` (sous-classe de ``JWTAuthentication``) et n'ajoute
    donc aucun schéma de sécurité → pas de bouton « Authorize » dans Swagger.
    On déclare le schéma Bearer (principal, utilisé par le dashboard et le mobile)
    plus le cookie d'accès httpOnly en second.
    """
    target_class = 'Mapapi.authentication.CookieJWTAuthentication'
    name = ['jwtAuth', 'cookieAuth']  # deux schémas : Bearer + cookie

    def get_security_definition(self, auto_schema):
        return [
            {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
                'description': (
                    "Token JWT d'accès. Obtenez-le via `POST /MapApi/login/` "
                    "(corps `{email, password}` → `{access, refresh}`), puis "
                    "cliquez sur **Authorize** et collez le token (sans le préfixe "
                    "`Bearer`). Durée de vie : 90 jours."
                ),
            },
            {
                'type': 'apiKey',
                'in': 'cookie',
                'name': 'access_token',
                'description': (
                    "Cookie httpOnly posé par `POST /MapApi/login/` "
                    "(utilisé en same-site / proxy ; le dashboard utilise le Bearer)."
                ),
            },
        ]
