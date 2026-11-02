"""Settings API DTOs (B6+)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceProfileOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    hidden: bool = False


class SourceProfileListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[dict[str, Any]] = Field(default_factory=list)
