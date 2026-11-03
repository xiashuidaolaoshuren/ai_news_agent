"""Bounded credential test probes (B10)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from ai_news_agent.credential_health import credential_name_to_source, health_version_for_source
from ai_news_agent.credentials import CredentialsProvider
from ai_news_agent.llm import build_chat_model

ProbeResultKind = Literal[
    "ok",
    "auth_error",
    "unavailable",
    "rate_limited",
    "timeout",
]

PROBE_TIMEOUT_SECONDS = 10.0

TESTABLE_CREDENTIAL_NAMES: frozenset[str] = frozenset(
    {
        "GITHUB_TOKEN",
        "HUGGINGFACE_TOKEN",
        "ZHIHU_ACCESS_SECRET",
        "llm",
    }
)

_BILIBILI_PREFIX = "BILIBILI_"

_REASON_OK = "Provider accepted the credential."
_REASON_AUTH = "Authentication failed."
_REASON_RATE = "Rate limited."
_REASON_TIMEOUT = "Request timed out."
_REASON_UNAVAILABLE = "Provider unavailable."


@dataclass(frozen=True)
class ProbeOutcome:
    result: ProbeResultKind
    reason: str


def classify_probe_outcome(
    *,
    status_code: int | None,
    timed_out: bool = False,
    github_rate_limit_exhausted: bool = False,
    zhihu_quota: bool = False,
) -> ProbeOutcome:
    if timed_out:
        return ProbeOutcome(result="timeout", reason=_REASON_TIMEOUT)
    if zhihu_quota:
        return ProbeOutcome(result="rate_limited", reason=_REASON_RATE)
    if status_code == 200:
        return ProbeOutcome(result="ok", reason=_REASON_OK)
    if status_code in (401, 403) and not github_rate_limit_exhausted:
        return ProbeOutcome(result="auth_error", reason=_REASON_AUTH)
    if status_code == 429 or github_rate_limit_exhausted:
        return ProbeOutcome(result="rate_limited", reason=_REASON_RATE)
    if status_code is None or status_code >= 500:
        return ProbeOutcome(result="unavailable", reason=_REASON_UNAVAILABLE)
    if status_code >= 400:
        return ProbeOutcome(result="unavailable", reason=_REASON_UNAVAILABLE)
    return ProbeOutcome(result="unavailable", reason=_REASON_UNAVAILABLE)


def _github_rate_limit_exhausted(resp: httpx.Response) -> bool:
    if resp.status_code != 403:
        return False
    remaining = resp.headers.get("x-ratelimit-remaining")
    if remaining is not None and remaining.strip() == "0":
        return True
    return False


async def probe_github(token: str, *, client: httpx.AsyncClient | None = None) -> ProbeOutcome:
    owns = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS)
    try:
        resp = await client.get(
            "https://api.github.com/rate_limit",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        return classify_probe_outcome(
            status_code=resp.status_code,
            github_rate_limit_exhausted=_github_rate_limit_exhausted(resp),
        )
    except httpx.TimeoutException:
        return classify_probe_outcome(status_code=None, timed_out=True)
    except httpx.RequestError:
        return classify_probe_outcome(status_code=None)
    finally:
        if owns:
            await client.aclose()


async def probe_huggingface(
    token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> ProbeOutcome:
    owns = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS)
    try:
        resp = await client.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {token}"},
        )
        return classify_probe_outcome(status_code=resp.status_code)
    except httpx.TimeoutException:
        return classify_probe_outcome(status_code=None, timed_out=True)
    except httpx.RequestError:
        return classify_probe_outcome(status_code=None)
    finally:
        if owns:
            await client.aclose()


def _zhihu_quota_envelope(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    code = data.get("Code", 0)
    message = str(data.get("Message") or "")
    if code in (0, "0", None):
        return False
    lowered = message.lower()
    return "quota" in lowered or "limit" in lowered


async def probe_zhihu(
    token: str,
    *,
    client: httpx.AsyncClient | None = None,
    base_url: str = "https://developer.zhihu.com",
) -> ProbeOutcome:
    owns = client is None
    if client is None:
        client = httpx.AsyncClient(base_url=base_url, timeout=PROBE_TIMEOUT_SECONDS)
    try:
        resp = await client.get(
            "/api/v1/content/zhihu_search",
            params={"Query": "credential-test", "Count": 1},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Timestamp": str(int(time.time())),
            },
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return classify_probe_outcome(status_code=resp.status_code)
            if isinstance(data, dict) and data.get("Code") not in (0, "0", None):
                if _zhihu_quota_envelope(data):
                    return classify_probe_outcome(status_code=resp.status_code, zhihu_quota=True)
                return classify_probe_outcome(status_code=401)
            return classify_probe_outcome(status_code=200)
        return classify_probe_outcome(status_code=resp.status_code)
    except httpx.TimeoutException:
        return classify_probe_outcome(status_code=None, timed_out=True)
    except httpx.RequestError:
        return classify_probe_outcome(status_code=None)
    finally:
        if owns:
            await client.aclose()


async def probe_llm(
    *,
    api_key: str,
    base_url: str | None,
    model: str | None,
    chat_model: Any | None = None,
) -> ProbeOutcome:
    try:
        model_obj = chat_model or build_chat_model(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        client = model_obj._client  # noqa: SLF001
        model_name = model_obj._model  # noqa: SLF001
        client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return classify_probe_outcome(status_code=200)
    except httpx.TimeoutException:
        return classify_probe_outcome(status_code=None, timed_out=True)
    except Exception as exc:  # noqa: BLE001 - map provider failures
        name = type(exc).__name__.lower()
        if "auth" in name or "permission" in name or "401" in str(exc):
            return classify_probe_outcome(status_code=401)
        if "rate" in name or "429" in str(exc):
            return classify_probe_outcome(status_code=429)
        if "timeout" in name:
            return classify_probe_outcome(status_code=None, timed_out=True)
        return classify_probe_outcome(status_code=503)


async def run_credential_test(
    name: str,
    provider: CredentialsProvider,
    *,
    http_client: httpx.AsyncClient | None = None,
    chat_model: Any | None = None,
) -> ProbeOutcome:
    if name.startswith(_BILIBILI_PREFIX):
        raise ValueError("Bilibili credential test is not supported")
    if name not in TESTABLE_CREDENTIAL_NAMES:
        raise ValueError(f"Unknown credential name: {name}")

    if name == "llm":
        llm = provider.resolve_llm()
        if llm.status == "unreadable":
            raise UnreadableCredentialError(name)
        if llm.status == "unset" or not llm.api_key:
            raise UnconfiguredCredentialError(name)
        return await probe_llm(
            api_key=llm.api_key,
            base_url=llm.base_url,
            model=llm.model,
            chat_model=chat_model,
        )

    resolved = provider.resolve(name)
    if resolved.status == "unreadable":
        raise UnreadableCredentialError(name)
    if resolved.status == "unset" or not resolved.value:
        raise UnconfiguredCredentialError(name)

    token = resolved.value
    if name == "GITHUB_TOKEN":
        return await probe_github(token, client=http_client)
    if name == "HUGGINGFACE_TOKEN":
        return await probe_huggingface(token, client=http_client)
    if name == "ZHIHU_ACCESS_SECRET":
        return await probe_zhihu(token, client=http_client)
    raise ValueError(f"Unknown credential name: {name}")


class UnconfiguredCredentialError(ValueError):
    """Credential has no effective value to test."""


class UnreadableCredentialError(RuntimeError):
    """Saved credential cannot be decrypted."""


def store_test_result(
    *,
    db_path: str | Any,
    name: str,
    provider: CredentialsProvider,
    outcome: ProbeOutcome,
) -> str:
    from pathlib import Path

    from ai_news_agent.credential_health import CredentialHealthStore

    source = credential_name_to_source(name)
    if source is None:
        raise ValueError(name)
    version = health_version_for_source(provider, source)
    store = CredentialHealthStore(Path(db_path))
    return store.record(
        source=source,
        credential_version=version,
        kind="test",
        result=outcome.result,
    )


__all__ = [
    "ProbeOutcome",
    "TESTABLE_CREDENTIAL_NAMES",
    "UnconfiguredCredentialError",
    "UnreadableCredentialError",
    "classify_probe_outcome",
    "probe_github",
    "probe_huggingface",
    "probe_llm",
    "probe_zhihu",
    "run_credential_test",
    "store_test_result",
]
