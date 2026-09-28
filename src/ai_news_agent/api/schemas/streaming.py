"""SSE event payload models (Milestone 8A.1 T14)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ai_news_agent.api.schemas.digests import DigestView
from ai_news_agent.models import ConnectorWarning


class StartedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    user_message_id: int


class ProgressPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str


class DeltaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class WorkflowErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    message: str
    detail: str | None = None


class DigestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    digest: DigestView
    markdown: str
    warnings: list[ConnectorWarning] = Field(default_factory=list)
    errors: list[WorkflowErrorPayload] = Field(default_factory=list)


class DonePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    message_id: int
    run_id: int | None
    path: str


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    code: str
    message: str
    correlation_id: str
