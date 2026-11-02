"""Session and message API DTOs (Milestone 8A.1 T14)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_news_agent.api.schemas.digests import DigestView
from ai_news_agent.collection_outcomes import CollectionOutcome
from ai_news_agent.models import ConnectorWarning


class SessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None
    connector_names: list[str] | None
    items_per_source: int | None
    created_at: datetime
    updated_at: datetime
    digest_count: int = 0
    active_request_id: str | None = None


class SessionListPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[SessionOut]
    next_cursor: str | None


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    connector_names: list[str] | None = None
    items_per_source: int | None = None


FollowupAction = Literal["deep_dive", "ask"]


class FollowupTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest_id: int
    display_rank: int


class ResolvedRequestOut(BaseModel):
    """Public, user-relevant options of one resolved digest request."""

    model_config = ConfigDict(extra="forbid")

    sources: list[str] = Field(default_factory=list)
    per_source: int | None = None
    counts: dict[str, str] = Field(default_factory=dict)
    timeframe: str | None = None
    topics: list[str] = Field(default_factory=list)
    language: str | None = None
    audience: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: str
    sequence: int
    role: str
    content: str
    run_id: int | None
    created_at: datetime
    digest_id: int | None = None
    warnings: list[ConnectorWarning] = Field(default_factory=list)
    digest: DigestView | None = None
    #: What a user message's digest run actually used, when it started one.
    request: ResolvedRequestOut | None = None
    followup_target: FollowupTarget | None = None
    followup_action: FollowupAction | None = None
    #: How the assistant message's digest run ended, when it saved one.
    collection_outcome: CollectionOutcome | None = None


class MessageListPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[MessageOut]
    next_cursor: str | None


class PostMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    client_request_id: str | None = Field(default=None)
    juya_item_mode: Literal["issue", "stories"] = "issue"
    followup_target: FollowupTarget | None = None
    followup_action: FollowupAction | None = None
    #: Start a fresh run from the resolution stored for this earlier user message.
    repeat_of_user_message_id: int | None = None
    #: With a repeat id: use this catalog source instead of the stored sources.
    replace_source: str | None = None

    @model_validator(mode="after")
    def _followup_target_and_action_paired(self) -> PostMessageBody:
        has_target = self.followup_target is not None
        has_action = self.followup_action is not None
        if has_target != has_action:
            raise ValueError(
                "followup_target and followup_action must both be present or both absent"
            )
        if self.replace_source is not None and self.repeat_of_user_message_id is None:
            raise ValueError(
                "replace_source requires repeat_of_user_message_id"
            )
        if self.repeat_of_user_message_id is not None and (has_target or has_action):
            raise ValueError(
                "repeat_of_user_message_id and followup fields are mutually exclusive"
            )
        return self


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
