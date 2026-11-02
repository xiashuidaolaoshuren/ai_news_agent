"""Encrypted credential overrides in SQLite (B9)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken

CredentialStatus = Literal["ui", "env", "unset", "unreadable"]

CREDENTIAL_ENV_NAMES: tuple[str, ...] = (
    "GITHUB_TOKEN",
    "HUGGINGFACE_TOKEN",
    "ZHIHU_ACCESS_SECRET",
    "BILIBILI_SESSDATA",
    "BILIBILI_BILI_JCT",
    "BILIBILI_BUVID3",
)

LLM_ENV_NAMES: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
)

_ALL_KNOWN_NAMES: frozenset[str] = frozenset(CREDENTIAL_ENV_NAMES) | frozenset(LLM_ENV_NAMES)

_SECRET_KEY_ENV = "AI_NEWS_AGENT_SECRET_KEY"


class MissingSecretKeyError(RuntimeError):
    """Raised when a write requires AI_NEWS_AGENT_SECRET_KEY but it is missing or invalid."""


class UnknownCredentialNameError(ValueError):
    """Raised when a credential name is not one of the supported env names."""


@dataclass(frozen=True)
class ResolvedCredential:
    status: CredentialStatus
    value: str | None
    last4: str | None
    version: str | None


@dataclass(frozen=True)
class ResolvedLlmConfig:
    status: CredentialStatus
    api_key: str | None
    base_url: str | None
    model: str | None
    last4: str | None
    version: str | None


@dataclass(frozen=True)
class CredentialStatusRow:
    name: str
    status: CredentialStatus
    last4: str | None
    version: str | None


def _version_from_ciphertext(ciphertext: str) -> str:
    return hashlib.sha256(ciphertext.encode("utf-8")).hexdigest()[:16]


def _last4(value: str) -> str:
    return value[-4:] if value else ""


class CredentialsProvider:
    """Resolve and persist Fernet-encrypted secrets in the B5 ``secrets`` table."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._environ = environ if environ is not None else os.environ

    def has_secret_key(self) -> bool:
        return self._fernet() is not None

    def save(self, name: str, value: str) -> None:
        self._validate_name(name)
        fernet = self._require_fernet()
        ciphertext = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        self._upsert_row(name, ciphertext)

    def delete(self, name: str) -> None:
        self._validate_name(name)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM secrets WHERE name = ?", (name,))

    def save_llm(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must not be blank")
        fernet = self._require_fernet()
        now = datetime.now(UTC).isoformat()
        rows: list[tuple[str, str]] = [(LLM_ENV_NAMES[0], fernet.encrypt(api_key.encode()).decode())]
        deletes: list[str] = []
        if base_url is not None:
            rows.append(
                (LLM_ENV_NAMES[1], fernet.encrypt(base_url.encode()).decode()),
            )
        else:
            deletes.append(LLM_ENV_NAMES[1])
        if model is not None:
            rows.append((LLM_ENV_NAMES[2], fernet.encrypt(model.encode()).decode()))
        else:
            deletes.append(LLM_ENV_NAMES[2])

        with sqlite3.connect(self._db_path) as conn:
            for name in deletes:
                conn.execute("DELETE FROM secrets WHERE name = ?", (name,))
            for name, ciphertext in rows:
                conn.execute(
                    """
                    INSERT INTO secrets (name, ciphertext, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                      ciphertext = excluded.ciphertext,
                      updated_at = excluded.updated_at
                    """,
                    (name, ciphertext, now),
                )
            conn.commit()

    def delete_llm(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            for name in LLM_ENV_NAMES:
                conn.execute("DELETE FROM secrets WHERE name = ?", (name,))

    def resolve(self, name: str) -> ResolvedCredential:
        self._validate_name(name)
        row = self._fetch_row(name)
        if row is None:
            env_val = self._environ.get(name)
            if env_val:
                return ResolvedCredential(
                    status="env",
                    value=env_val,
                    last4=_last4(env_val),
                    version=None,
                )
            return ResolvedCredential(status="unset", value=None, last4=None, version=None)

        ciphertext = row["ciphertext"]
        version = _version_from_ciphertext(ciphertext)
        plain = self._decrypt(ciphertext)
        if plain is None:
            return ResolvedCredential(
                status="unreadable",
                value=None,
                last4=None,
                version=version,
            )
        return ResolvedCredential(
            status="ui",
            value=plain,
            last4=_last4(plain),
            version=version,
        )

    def resolve_llm(self) -> ResolvedLlmConfig:
        parts = {name: self.resolve(name) for name in LLM_ENV_NAMES}
        version = self._llm_version(parts)
        if any(p.status == "unreadable" for p in parts.values()):
            return ResolvedLlmConfig(
                status="unreadable",
                api_key=None,
                base_url=None,
                model=None,
                last4=None,
                version=version,
            )

        api = parts["OPENAI_API_KEY"]
        base = parts["OPENAI_BASE_URL"]
        model_part = parts["OPENAI_MODEL"]

        if api.status == "ui":
            status: CredentialStatus = "ui"
        elif api.status == "env":
            status = "env"
        elif self._environ.get("OPENAI_API_KEY"):
            status = "env"
        else:
            status = "unset"

        return ResolvedLlmConfig(
            status=status,
            api_key=api.value,
            base_url=base.value,
            model=model_part.value,
            last4=api.last4 if api.status in ("ui", "env") else None,
            version=version,
        )

    def statuses(self) -> list[CredentialStatusRow]:
        rows: list[CredentialStatusRow] = []
        for name in CREDENTIAL_ENV_NAMES:
            resolved = self.resolve(name)
            rows.append(
                CredentialStatusRow(
                    name=name,
                    status=resolved.status,
                    last4=resolved.last4 if resolved.status in ("ui", "env") else None,
                    version=resolved.version,
                )
            )
        llm = self.resolve_llm()
        rows.append(
            CredentialStatusRow(
                name="llm",
                status=llm.status,
                last4=llm.last4 if llm.status in ("ui", "env") else None,
                version=llm.version,
            )
        )
        return rows

    def _llm_version(self, parts: dict[str, ResolvedCredential]) -> str | None:
        versions: list[str] = []
        for name in LLM_ENV_NAMES:
            row = self._fetch_row(name)
            if row is not None:
                versions.append(_version_from_ciphertext(row["ciphertext"]))
        if not versions:
            return None
        combined = "|".join(sorted(versions))
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _validate_name(self, name: str) -> None:
        if name not in _ALL_KNOWN_NAMES:
            raise UnknownCredentialNameError(name)

    def _fernet(self) -> Fernet | None:
        raw = self._environ.get(_SECRET_KEY_ENV)
        if not raw:
            return None
        try:
            return Fernet(raw.encode("utf-8"))
        except (ValueError, TypeError):
            return None

    def _require_fernet(self) -> Fernet:
        fernet = self._fernet()
        if fernet is None:
            raise MissingSecretKeyError(_SECRET_KEY_ENV)
        return fernet

    def _decrypt(self, ciphertext: str) -> str | None:
        fernet = self._fernet()
        if fernet is None:
            return None
        try:
            return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return None

    def _fetch_row(self, name: str) -> dict[str, Any] | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT name, ciphertext, updated_at FROM secrets WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def _upsert_row(self, name: str, ciphertext: str) -> None:
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO secrets (name, ciphertext, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                  ciphertext = excluded.ciphertext,
                  updated_at = excluded.updated_at
                """,
                (name, ciphertext, now),
            )
            conn.commit()


__all__ = [
    "CREDENTIAL_ENV_NAMES",
    "LLM_ENV_NAMES",
    "CredentialStatusRow",
    "CredentialsProvider",
    "MissingSecretKeyError",
    "ResolvedCredential",
    "ResolvedLlmConfig",
    "UnknownCredentialNameError",
]
