"""Owner-access ASGI middleware (B11)."""

from __future__ import annotations

import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ai_news_agent.access import AccessConfig

_API_PREFIX = "/api/v1"
_HEALTH_PATH = "/api/v1/health"
_CREDENTIALS_PREFIX = "/api/v1/settings/credentials"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_CREDENTIAL_WRITE_METHODS = frozenset({"PUT", "DELETE"})


def _bearer_token(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() != b"authorization":
            continue
        text = value.decode("latin-1").strip()
        scheme, _, token = text.partition(" ")
        token = token.strip()
        if scheme.lower() == "bearer" and token:
            return token
        return None
    return None


class OwnerAccessMiddleware:
    """Require the owner bearer token, or loopback-only credential writes.

    A configured token applies to every ``/api/v1`` route except ``/health``.
    Without a token (local mode), credential writes accept loopback clients
    only. CORS stays a browser policy, not authentication.
    """

    def __init__(self, app: ASGIApp, *, access: AccessConfig) -> None:
        self.app = app
        self._access = access

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            denial = self._denial(scope)
            if denial is not None:
                detail, status_code, headers = denial
                response = JSONResponse(
                    {"detail": detail}, status_code=status_code, headers=headers
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _denial(
        self, scope: Scope
    ) -> tuple[str, int, dict[str, str]] | None:
        path = str(scope.get("path", ""))
        if not path.startswith(_API_PREFIX) or path == _HEALTH_PATH:
            return None
        if self._access.access_token is not None:
            return self._token_denial(scope)
        return self._loopback_write_denial(scope, path)

    def _token_denial(
        self, scope: Scope
    ) -> tuple[str, int, dict[str, str]] | None:
        provided = _bearer_token(scope)
        if provided is None:
            return ("Missing bearer token", 401, {"WWW-Authenticate": "Bearer"})
        expected = self._access.access_token or ""
        if not secrets.compare_digest(
            provided.encode("utf-8"), expected.encode("utf-8")
        ):
            return ("Invalid bearer token", 401, {"WWW-Authenticate": "Bearer"})
        return None

    def _loopback_write_denial(
        self, scope: Scope, path: str
    ) -> tuple[str, int, dict[str, str]] | None:
        method = str(scope.get("method", ""))
        if method not in _CREDENTIAL_WRITE_METHODS:
            return None
        if not path.startswith(_CREDENTIALS_PREFIX):
            return None
        client = scope.get("client")
        host = client[0] if client else None
        if host not in _LOOPBACK_HOSTS:
            return (
                "Credential writes are allowed from loopback clients only",
                403,
                {},
            )
        return None


__all__ = ["OwnerAccessMiddleware"]
