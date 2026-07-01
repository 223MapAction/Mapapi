"""Authentification des WebSockets par le JWT (cookie httpOnly ou ?token=).

Le navigateur envoie automatiquement le cookie d'accès lors du handshake WS vers
le domaine backend ; on le valide pour peupler scope['user']. Repli possible sur
un paramètre de requête ``?token=`` (utile pour le mobile/Bearer)."""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _get_user(user_id):
    from .models import User
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


def _token_from_scope(scope):
    # 1. cookie httpOnly access_token
    for name, value in scope.get('headers', []):
        if name == b'cookie':
            cookies = value.decode()
            for part in cookies.split(';'):
                k, _, v = part.strip().partition('=')
                if k == settings.AUTH_COOKIE_ACCESS:
                    return v
    # 2. repli ?token=
    qs = parse_qs((scope.get('query_string') or b'').decode())
    if 'token' in qs:
        return qs['token'][0]
    return None


class JWTCookieAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope['user'] = AnonymousUser()
        raw = _token_from_scope(scope)
        if raw:
            try:
                access = AccessToken(raw)
                scope['user'] = await _get_user(access['user_id'])
            except (TokenError, KeyError):
                scope['user'] = AnonymousUser()
        return await super().__call__(scope, receive, send)
