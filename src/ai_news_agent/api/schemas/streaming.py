"""SSE event payload models (Milestone 8A.1 T14)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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
    digest_id: int
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


class StartedStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["started"] = "started"
    data: StartedPayload


class ProgressStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["progress"] = "progress"
    data: ProgressPayload


class DeltaStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["delta"] = "delta"
    data: DeltaPayload


class DigestStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["digest"] = "digest"
    data: DigestPayload


class DoneStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["done"] = "done"
    data: DonePayload


class ErrorStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["error"] = "error"
    data: ErrorPayload


_STREAM_EVENT_UNION = Annotated[
    Union[
        StartedStreamEvent,
        ProgressStreamEvent,
        DeltaStreamEvent,
        DigestStreamEvent,
        DoneStreamEvent,
        ErrorStreamEvent,
    ],
    Field(discriminator="event"),
]


def session_message_stream_openapi_schema() -> dict[str, object]:
    """OpenAPI schema for one SSE JSON data frame on session message POST."""
    return TypeAdapter(_STREAM_EVENT_UNION).json_schema(
        ref_template="#/components/schemas/{model}",
    )
