"""History HTTP DTOs (Milestone 8A.1 T16)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ai_news_agent.api.schemas.digests import DigestEntryViewUnion
from ai_news_agent.models import SourceKind


class HistoricalItemRefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    digest_id: int
    run_id: int
    entry_id: int
    rank: int


class HistorySearchMatchOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: HistoricalItemRefOut
    generated_at: datetime
    source_kind: SourceKind
    title: str
    url: str
    excerpt: str | None
    score: float


class HistorySearchResultOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[HistorySearchMatchOut]
    scanned_count: int
    archive_truncated: bool
    caveats: list[str]


class HistoryItemShowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    markdown: str
    entry: DigestEntryViewUnion | None = None