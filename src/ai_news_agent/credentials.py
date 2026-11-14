"""Encrypted credential overrides in SQLite (B9)."""

from __future__ import annotations

import getpass
import hashlib
import os
import sqlite3
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken

CredentialStatus = Literal["ui", "env", "unset", "unreadable"]

KeyFileStatus = Literal[
    "env",
    "existing",
    "created",
    "invalid",
    "recovery_required",
    "unavailable",
]

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


def key_file_path_for(db_path: Path | str) -> Path:
    """Return the sidecar key path beside *db_path*: ``<database name>.key``."""
    resolved = Path(db_path).expanduser().resolve()
    return resolved.parent / f"{resolved.name}.key"


def _protect_owner_only(path: Path) -> None:
    """Restrict *path* to the current owner before key bytes are written."""
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{getpass.getuser()}:F",
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError("could not restrict key-file permissions") from exc
        return
    os.chmod(path, 0o600)


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
        key_file: Path | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._environ = environ if environ is not None else os.environ
        self._key_file = key_file

    def has_secret_key(self) -> bool:
        return self._fernet() is not None

    def bootstrap_key_file(self) -> KeyFileStatus:
        """Resolve the env key or an existing sidecar, creating one only when safe."""
        raw = self._environ.get(_SECRET_KEY_ENV)
        if raw and raw.strip():
            try:
                Fernet(raw.encode("utf-8"))
            except (ValueError, TypeError):
                return "invalid"
            return "env"
        if self._key_file is None:
            return "unavailable"
        try:
            info: os.stat_result | None = os.lstat(self._key_file)
        except FileNotFoundError:
            info = None
        except (OSError, ValueError):
            return "unavailable"
        if info is not None:
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                return "invalid"
            data = self._read_key_file()
            if data is None:
                return "invalid"
            try:
                Fernet(data)
            except (ValueError, TypeError):
                return "invalid"
            return "existing"
        if self._has_encrypted_rows():
            return "recovery_required"
        return self._create_key_file()

    def _has_encrypted_rows(self) -> bool:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute("SELECT 1 FROM secrets LIMIT 1").fetchone()
        except sqlite3.Error:
            # Cannot prove the database holds no ciphertext; never rotate blindly.
            return True
        return row is not None

    def _create_key_file(self) -> KeyFileStatus:
        if self._key_file is None:
            return "unavailable"
        try:
            self._key_file.parent.mkdir(parents=True, exist_ok=True)
            fd, raw_tmp = tempfile.mkstemp(
                prefix=f".{self._key_file.name}.",
                suffix=".key",
                dir=self._key_file.parent,
            )
        except OSError:
            return "unavailable"
        os.close(fd)
        tmp = Path(raw_tmp)
        try:
            try:
                _protect_owner_only(tmp)
                with tmp.open("wb") as handle:
                    handle.write(Fernet.generate_key() + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError:
                return "unavailable"
            try:
                os.link(tmp, self._key_file)
            except FileExistsError:
                data = self._read_key_file()
                if data is None:
                    return "invalid"
                try:
                    Fernet(data)
                except (ValueError, TypeError):
                    return "invalid"
                return "existing"
            except OSError:
                return "unavailable"
            return "created"
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

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
        if raw and raw.strip():
            # A nonblank env key is authoritative; a malformed one stays unusable
            # rather than silently falling back to the sidecar.
            try:
                return Fernet(raw.encode("utf-8"))
            except (ValueError, TypeError):
                return None
        data = self._read_key_file()
        if data is None:
            return None
        try:
            return Fernet(data)
        except (ValueError, TypeError):
            return None

    def _read_key_file(self) -> bytes | None:
        if self._key_file is None:
            return None
        try:
            info = os.lstat(self._key_file)
        except (OSError, ValueError):
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        try:
            raw = self._key_file.read_bytes()
        except OSError:
            return None
        data = raw.strip()
        return data or None

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
    "KeyFileStatus",
    "MissingSecretKeyError",
    "key_file_path_for",
    "ResolvedCredential",
    "ResolvedLlmConfig",
    "UnknownCredentialNameError",
]
