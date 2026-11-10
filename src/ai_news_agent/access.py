"""Server access policy: remote mode, owner token, CORS origins (B11)."""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

REMOTE_ENV = "AI_NEWS_AGENT_REMOTE"
ACCESS_TOKEN_ENV = "AI_NEWS_AGENT_ACCESS_TOKEN"
CORS_ORIGINS_ENV = "AI_NEWS_AGENT_CORS_ORIGINS"
ALLOW_LOCAL_LLM_ENV = "AI_NEWS_AGENT_ALLOW_LOCAL_LLM"

LOOPBACK_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE_VALUES


def _cors_origins(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return LOOPBACK_CORS_ORIGINS
    origins = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not origins:
        return LOOPBACK_CORS_ORIGINS
    for origin in origins:
        if "*" in origin:
            raise RuntimeError(
                "AI_NEWS_AGENT_CORS_ORIGINS must not contain wildcard origins."
            )
    return origins


@dataclass(frozen=True)
class AccessConfig:
    """Resolved owner-access settings for one server process."""

    remote: bool = False
    access_token: str | None = None
    cors_origins: tuple[str, ...] = LOOPBACK_CORS_ORIGINS
    allow_local_llm: bool = False

    @classmethod
    def from_environ(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        remote_flag: bool = False,
    ) -> "AccessConfig":
        """Resolve from ``AI_NEWS_AGENT_*`` settings; raise when misconfigured."""
        env = os.environ if environ is None else environ
        remote = remote_flag or _truthy(env.get(REMOTE_ENV))
        raw_token = env.get(ACCESS_TOKEN_ENV)
        token = raw_token.strip() if raw_token and raw_token.strip() else None
        if remote and token is None:
            raise RuntimeError(
                "Remote mode requires AI_NEWS_AGENT_ACCESS_TOKEN to be set."
            )
        return cls(
            remote=remote,
            access_token=token,
            cors_origins=_cors_origins(env.get(CORS_ORIGINS_ENV)),
            allow_local_llm=_truthy(env.get(ALLOW_LOCAL_LLM_ENV)),
        )


def _resolve_host_addresses(host: str) -> list[str]:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise ValueError(
                "LLM base URL host could not be resolved in remote mode"
            ) from exc
        addresses = sorted({str(info[4][0]) for info in infos})
        if not addresses:
            raise ValueError(
                "LLM base URL host could not be resolved in remote mode"
            )
        return addresses
    return [host]


def _require_public_address(host: str) -> None:
    for address in _resolve_host_addresses(host):
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(
                "LLM base URL must use a public address in remote mode"
            )


def validate_llm_base_url(url: str, *, allow_local: bool) -> None:
    """Reject a remote-mode LLM endpoint that is not public HTTPS."""
    if allow_local:
        return
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ValueError("LLM base URL must be HTTPS in remote mode")
    host = parts.hostname
    if not host:
        raise ValueError("LLM base URL must include a host in remote mode")
    _require_public_address(host)


class LlmEndpointGuard:
    """Hold one LLM request to the remote-mode endpoint rule on every hop."""

    def __init__(self, *, allow_local: bool = False) -> None:
        self._allow_local = allow_local

    def assert_url(self, url: str) -> None:
        validate_llm_base_url(url, allow_local=self._allow_local)

    def sync_request_hook(self, request: httpx.Request) -> None:
        self.assert_url(str(request.url))

    async def async_request_hook(self, request: httpx.Request) -> None:
        self.assert_url(str(request.url))


def llm_url_guard(access: AccessConfig) -> LlmEndpointGuard | None:
    """Return the guard a remote-mode server must apply to LLM traffic."""
    if not access.remote or access.allow_local_llm:
        return None
    return LlmEndpointGuard()


__all__ = [
    "ACCESS_TOKEN_ENV",
    "ALLOW_LOCAL_LLM_ENV",
    "CORS_ORIGINS_ENV",
    "LOOPBACK_CORS_ORIGINS",
    "REMOTE_ENV",
    "AccessConfig",
    "LlmEndpointGuard",
    "llm_url_guard",
    "validate_llm_base_url",
]
