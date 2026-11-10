"""Credential health observations (B10)."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ai_news_agent.collection_outcomes import SOURCE_FAILURE_CODES
from ai_news_agent.credentials import CredentialsProvider
from ai_news_agent.sources import _BILIBILI_CREDENTIAL_NAMES
from ai_news_agent.models import ConnectorWarning

HealthKind = Literal["connector", "test"]
HealthResult = Literal[
    "ok",
    "auth_error",
    "unavailable",
    "rate_limited",
    "timeout",
]

_CREDENTIAL_NAME_TO_SOURCE: dict[str, str] = {
    "GITHUB_TOKEN": "github",
    "HUGGINGFACE_TOKEN": "huggingface",
    "ZHIHU_ACCESS_SECRET": "zhihu",
    "BILIBILI_SESSDATA": "bilibili",
    "BILIBILI_BILI_JCT": "bilibili",
    "BILIBILI_BUVID3": "bilibili",
    "llm": "llm",
}

_HEALTH_SOURCES: frozenset[str] = frozenset(
    {"github", "huggingface", "zhihu", "bilibili", "llm"}
)

_AUTH_WARNING_CODES: frozenset[str] = frozenset(
    {
        "auth_missing",
        "auth_required_missing",
        "auth_required_rejected",
        "credential_unreadable",
    }
)

_TIMEOUT_WARNING_CODES: frozenset[str] = frozenset({"timeout"})


@dataclass(frozen=True)
class HealthObservation:
    source: str
    observed_at: str
    credential_version: str
    kind: HealthKind
    result: str


@dataclass(frozen=True)
class HealthSummary:
    current: str | None
    stale: bool
    credential_version: str
    observed_at: str | None
    kind: HealthKind | None


def credential_name_to_source(name: str) -> str | None:
    return _CREDENTIAL_NAME_TO_SOURCE.get(name)


def health_version_for_source(provider: CredentialsProvider, source: str) -> str:
    if source == "llm":
        llm = provider.resolve_llm()
        if llm.version is not None:
            return llm.version
        if llm.status == "env":
            return "env"
        if llm.status == "unreadable":
            return llm.version or "unreadable"
        return "unset"

    if source == "bilibili":
        parts = [provider.resolve(name) for name in _BILIBILI_CREDENTIAL_NAMES]
        if any(p.status == "unreadable" for p in parts):
            row_versions = [p.version for p in parts if p.version]
            if row_versions:
                combined = "|".join(sorted(row_versions))
                return hashlib.sha256(combined.encode()).hexdigest()[:16]
            return "unreadable"
        versions = [p.version for p in parts if p.version is not None]
        if versions:
            combined = "|".join(sorted(versions))
            return hashlib.sha256(combined.encode()).hexdigest()[:16]
        if any(p.status == "env" for p in parts):
            return "env"
        return "unset"

    env_name = {
        "github": "GITHUB_TOKEN",
        "huggingface": "HUGGINGFACE_TOKEN",
        "zhihu": "ZHIHU_ACCESS_SECRET",
    }.get(source)
    if env_name is None:
        return "unset"
    resolved = provider.resolve(env_name)
    if resolved.version is not None:
        return resolved.version
    if resolved.status == "env":
        return "env"
    if resolved.status == "unreadable":
        return resolved.version or "unreadable"
    return "unset"


def map_warnings_to_connector_result(
    source: str,
    warnings: list[ConnectorWarning],
) -> HealthResult:
    source_warnings = [w for w in warnings if w.connector == source]
    if not source_warnings:
        return "ok"
    codes = {w.code for w in source_warnings}
    if "rate_limited" in codes or "quota_exhausted" in codes:
        return "rate_limited"
    if codes & _AUTH_WARNING_CODES:
        return "auth_error"
    if codes & _TIMEOUT_WARNING_CODES:
        return "timeout"
    if any(code in SOURCE_FAILURE_CODES for code in codes):
        return "unavailable"
    return "unavailable"


class CredentialHealthStore:
    """Persist and summarize rows in the B5 ``credential_health`` table."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def record(
        self,
        *,
        source: str,
        credential_version: str,
        kind: HealthKind,
        result: str,
        observed_at: str | None = None,
    ) -> str:
        ts = observed_at or datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO credential_health
                  (source, observed_at, credential_version, kind, result)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, ts, credential_version, kind, result),
            )
            conn.commit()
        return ts

    def latest_for_version(
        self,
        source: str,
        credential_version: str,
    ) -> HealthObservation | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT source, observed_at, credential_version, kind, result
                FROM credential_health
                WHERE source = ? AND credential_version = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source, credential_version),
            ).fetchone()
        if row is None:
            return None
        return HealthObservation(
            source=row["source"],
            observed_at=row["observed_at"],
            credential_version=row["credential_version"],
            kind=row["kind"],
            result=row["result"],
        )

    def has_any_for_source(self, source: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM credential_health WHERE source = ? LIMIT 1",
                (source,),
            ).fetchone()
        return row is not None

    def has_rows_for_other_versions(self, source: str, current_version: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM credential_health
                WHERE source = ? AND credential_version != ?
                LIMIT 1
                """,
                (source, current_version),
            ).fetchone()
        return row is not None

    def summary_for_source(
        self,
        source: str,
        current_version: str,
    ) -> HealthSummary:
        latest = self.latest_for_version(source, current_version)
        if latest is not None:
            return HealthSummary(
                current=latest.result,
                stale=False,
                credential_version=current_version,
                observed_at=latest.observed_at,
                kind=latest.kind,
            )
        stale = self.has_rows_for_other_versions(source, current_version)
        return HealthSummary(
            current=None,
            stale=stale,
            credential_version=current_version,
            observed_at=None,
            kind=None,
        )


def record_connector_health_from_digest(
    *,
    store: CredentialHealthStore,
    provider: CredentialsProvider,
    warnings: list[ConnectorWarning],
    connector_names: set[str],
) -> None:
    for source in connector_names:
        if source not in _HEALTH_SOURCES:
            continue
        version = health_version_for_source(provider, source)
        result = map_warnings_to_connector_result(source, warnings)
        store.record(
            source=source,
            credential_version=version,
            kind="connector",
            result=result,
        )


def juya_unchecked_summary() -> HealthSummary:
    return HealthSummary(
        current=None,
        stale=False,
        credential_version="unset",
        observed_at=None,
        kind=None,
    )


def summary_for_catalog_source(
    store: CredentialHealthStore,
    provider: CredentialsProvider,
    source: str,
) -> HealthSummary:
    if source == "juya":
        return juya_unchecked_summary()
    if source not in _HEALTH_SOURCES:
        return juya_unchecked_summary()
    version = health_version_for_source(provider, source)
    return store.summary_for_source(source, version)


__all__ = [
    "CredentialHealthStore",
    "HealthObservation",
    "HealthSummary",
    "credential_name_to_source",
    "health_version_for_source",
    "map_warnings_to_connector_result",
    "record_connector_health_from_digest",
    "summary_for_catalog_source",
]
