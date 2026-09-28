"""Session and message API DTOs (Milestone 8A.1 T14)."""

from __future__ import annotations

from datetime import datetime

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
