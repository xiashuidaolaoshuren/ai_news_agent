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
