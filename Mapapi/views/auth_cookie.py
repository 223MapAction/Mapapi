"""Vues d'authentification déposant le JWT dans des cookies httpOnly.

login → pose access_token + refresh_token (httpOnly) + un cookie csrftoken (lisible
par le SPA pour renvoyer X-CSRFToken). refresh → relit le refresh depuis le cookie.
logout → efface les cookies. Les tokens restent aussi dans le corps JSON pour le
mobile (Bearer) et la transition.
"""
from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from drf_spectacular.utils import (
    extend_schema, OpenApiExample, OpenApiResponse, inline_serializer,
)
from rest_framework import serializers


def _set_auth_cookies(request, response, access=None, refresh=None):
    """Pose les cookies JWT httpOnly. Secure + SameSite=None en HTTPS (cross-site
    prod : front et back sur des domaines différents) ; Lax + non-secure en HTTP local."""
    secure = request.is_secure()
    samesite = 'None' if secure else 'Lax'
    common = dict(httponly=True, secure=secure, samesite=samesite, path='/')
    if access:
        response.set_cookie(
            settings.AUTH_COOKIE_ACCESS, access,
            max_age=settings.AUTH_COOKIE_ACCESS_MAX_AGE, **common,
        )
    if refresh:
        response.set_cookie(
            settings.AUTH_COOKIE_REFRESH, refresh,
            max_age=settings.AUTH_COOKIE_REFRESH_MAX_AGE, **common,
        )


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CookieTokenObtainPairView(TokenObtainPairView):
    """POST /login/ — pose les cookies httpOnly + renvoie aussi les tokens (mobile)."""

    # Le login établit l'authentification (via identifiants) ; il ne doit PAS faire
    # tourner l'auth par cookie (sinon un cookie résiduel déclencherait une
    # vérif CSRF et bloquerait la reconnexion).
    authentication_classes = []

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_login',
        summary="Connexion (obtention des tokens JWT)",
        description=(
            "Authentifie un utilisateur par `email` + `password` et renvoie les tokens "
            "JWT `access`/`refresh` dans le corps (utilisés par le mobile via "
            "`Authorization: Bearer`). Pose aussi ces tokens dans des cookies httpOnly "
            "(`access_token`, `refresh_token`) et ajoute un `csrftoken` dans le corps "
            "(le SPA cross-site le renvoie via l'en-tête `X-CSRFToken`). Endpoint public ; "
            "également monté sur `POST /api/token/` (alias)."
        ),
        request=inline_serializer(
            name='AuthLoginRequest',
            fields={
                'email': serializers.EmailField(),
                'password': serializers.CharField(write_only=True),
            },
        ),
        responses={
            200: inline_serializer(
                name='AuthLoginResponse',
                fields={
                    'access': serializers.CharField(),
                    'refresh': serializers.CharField(),
                    'csrftoken': serializers.CharField(),
                },
            ),
            401: OpenApiResponse(description="Identifiants invalides (`{detail}`)."),
        },
        examples=[
            OpenApiExample(
                'Connexion',
                value={'email': 'agent@example.org', 'password': 'motdepasse'},
                request_only=True,
            ),
            OpenApiExample(
                'Tokens renvoyés',
                value={
                    'access': 'eyJhbGciOiJI...',
                    'refresh': 'eyJhbGciOiJI...',
                    'csrftoken': 'p0Tk...CSRF',
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            _set_auth_cookies(
                request, response,
                access=response.data.get('access'),
                refresh=response.data.get('refresh'),
            )
            # Renvoie aussi le token CSRF DANS LE CORPS : en cross-site le SPA ne
            # peut pas lire le cookie csrftoken (domaine backend) → il lit cette
            # valeur et la renvoie en X-CSRFToken sur les écritures.
            response.data['csrftoken'] = get_token(request)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """POST /token/refresh/ — relit le refresh depuis le corps OU le cookie."""

    # Le refresh s'authentifie via le refresh token lui-même, pas via l'access
    # cookie → pas d'auth par cookie ici (donc pas de blocage CSRF).
    authentication_classes = []

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_token_refresh',
        summary="Rafraîchir le token d'accès",
        description=(
            "Renvoie un nouveau token `access` à partir d'un `refresh` valide. Le refresh "
            "est lu depuis le corps `{refresh}` ou, à défaut, depuis le cookie httpOnly "
            "`refresh_token`. Met aussi à jour les cookies d'authentification. Endpoint public."
        ),
        request=inline_serializer(
            name='AuthTokenRefreshRequest',
            fields={'refresh': serializers.CharField(required=False)},
        ),
        responses={
            200: inline_serializer(
                name='AuthTokenRefreshResponse',
                fields={'access': serializers.CharField()},
            ),
            401: OpenApiResponse(description="Refresh token invalide ou expiré (`{detail}`)."),
        },
    )
    def post(self, request, *args, **kwargs):
        refresh = request.data.get('refresh') or request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        serializer = self.get_serializer(data={'refresh': refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        _set_auth_cookies(
            request, response,
            access=serializer.validated_data.get('access'),
            refresh=serializer.validated_data.get('refresh'),
        )
        return response


class CookieLogoutView(APIView):
    """POST /logout/ — efface les cookies d'authentification.

    Sans authentification ni CSRF : la déconnexion (effacer les cookies) doit
    toujours réussir, même avec un token expiré/absent."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_logout',
        summary="Déconnexion",
        description=(
            "Efface les cookies d'authentification httpOnly (`access_token`, `refresh_token`). "
            "Sans authentification ni CSRF : la déconnexion réussit toujours, même sans token valide."
        ),
        request=None,
        responses={200: OpenApiResponse(description="Déconnecté (`{detail}`).")},
    )
    def post(self, request):
        response = Response({'detail': 'Déconnecté.'}, status=status.HTTP_200_OK)
        response.delete_cookie(settings.AUTH_COOKIE_ACCESS, path='/')
        response.delete_cookie(settings.AUTH_COOKIE_REFRESH, path='/')
        return response
