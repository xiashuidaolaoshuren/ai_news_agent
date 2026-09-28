"""Session and message API DTOs (Milestone 8A.1 T14)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_news_agent.api.schemas.digests import DigestView


class SessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None
    connector_names: list[str] | None
    items_per_source: int | None
    created_at: datetime
    updated_at: datetime


class SessionListPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[SessionOut]
    next_cursor: str | None


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    connector_names: list[str] | None = None
    items_per_source: int | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: str
    sequence: int
    role: str
    content: str
    run_id: int | None
    created_at: datetime
    digest: DigestView | None = None


class MessageListPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[MessageOut]
    next_cursor: str | None


class PostMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    client_request_id: str | None = Field(default=None)


MatchKind = Literal["title", "user", "assistant"]


class SessionSearchHitOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    title: str | None
    updated_at: datetime
    match_kind: MatchKind
    message_id: int | None
    excerpt: str


class SessionSearchPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hits: list[SessionSearchHitOut]
    next_cursor: str | None


class RequestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    status: str
    user_message_id: int
    assistant_message_id: int | None
    run_id: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
