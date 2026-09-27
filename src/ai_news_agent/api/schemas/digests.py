"""DigestView API DTOs (Milestone 8A.1 T11)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_news_agent.models import Digest, FollowUpAction, NewsItem, SourceKind


class DigestEntryView(BaseModel):
    """Common digest entry fields exposed to the API."""

    model_config = ConfigDict(extra="ignore")

    source_kind: Literal[
        SourceKind.GITHUB,
        SourceKind.BILIBILI,
        SourceKind.JUYA,
        SourceKind.ZHIHU,
    ]
    source_id: str
    title: str
    source_name: str
    source_url: str
    summary: str
    why_it_matters: str
    background_knowledge: str
    follow_up_action: FollowUpAction
    confidence_caveat: str | None = None
    display_rank: int


class FamilyVariant(BaseModel):
    """Summary-only Hugging Face family variant for rich presentation."""

    model_config = ConfigDict(extra="ignore")

    source_id: str
    title: str
    url: str | None = None
    downloads_30d: int | None = None
    likes: int | None = None


class HuggingFaceDigestEntryView(DigestEntryView):
    """Hugging Face digest entry with whitelisted family metrics."""

    source_kind: Literal[SourceKind.HUGGINGFACE] = SourceKind.HUGGINGFACE
    trending_score: float | int | None = None
    downloads_30d: int | None = None
    likes: int | None = None
    pipeline_tag: str | None = None
    family_variants: list[FamilyVariant] = Field(default_factory=list)


DigestEntryViewUnion = Annotated[
    DigestEntryView | HuggingFaceDigestEntryView,
    Field(discriminator="source_kind"),
]


class DigestView(BaseModel):
    """API projection of a saved digest plus selected news evidence."""

    model_config = ConfigDict(extra="ignore")

    generated_at: datetime
    timeframe: str | None = None
    topics: list[str] = Field(default_factory=list)
    entries: list[DigestEntryViewUnion] = Field(default_factory=list)


def build_digest_view(
    digest: Digest,
    *,
    news_items: list[NewsItem] | None = None,
) -> DigestView:
    """Map a saved digest and optional news evidence to a DigestView DTO."""
    from ai_news_agent.services.digest_views import build_digest_view_payload

    return DigestView.model_validate(
        build_digest_view_payload(digest, news_items=news_items)
    )
