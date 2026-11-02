"""Settings API DTOs (B6+)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

OutputLanguageSetting = Literal["source_default", "en", "zh-CN"]


class SourceProfileOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    hidden: bool = False


class SourceProfileListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[dict[str, Any]] = Field(default_factory=list)


class LanguageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: OutputLanguageSetting


class LanguageUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: OutputLanguageSetting


CredentialStatusValue = Literal["ui", "env", "unset", "unreadable"]


class CredentialStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: CredentialStatusValue
    last4: str | None = None
    version: str | None = None


class CredentialsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret_key_configured: bool
    credentials: list[CredentialStatusOut] = Field(default_factory=list)


class CredentialUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class LlmCredentialUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str
    base_url: str | None = None
    model: str | None = None
