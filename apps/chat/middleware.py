"""
WebSocket Authentication Middleware for Jobraker
Handles token-based authentication for WebSocket connections
"""

import json
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_key):
    """
    Get user from JWT token
    """
    try:
        # Validate the token
        UntypedToken(token_key)

        # Decode the token to get user information
        decoded_data = jwt_decode(token_key, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = decoded_data.get("user_id")

        if user_id:
            user = User.objects.get(id=user_id)
            return user
    except (InvalidToken, TokenError, User.DoesNotExist, Exception):
        pass

    return AnonymousUser()


class TokenAuthMiddleware:
    """
    Token authorization middleware for Django Channels
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Parse query string for token
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)

        # Get token from query parameters
        token = None
        if "token" in query_params:
            token = query_params["token"][0]

        # If no token in query params, check headers
        if not token:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        # Get user from token
        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    """
    Middleware stack that includes token authentication
    """
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))
