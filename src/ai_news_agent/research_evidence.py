"""Shared research evidence models (plan R3).

Hand-constructible observations for fetch, loop, citations, and records.
No I/O, ID minting, or budgets in this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_news_agent.research_scope import ApprovedResearchScope, Relationship
from ai_news_agent.tools.schemas import ToolObservation

RetrievalOutcome = Literal["retrieved", "inaccessible", "refused", "failed"]
ExtractionCompleteness = Literal["complete", "truncated", "unsupported", "unsuccessful"]


class ResearchPassage(BaseModel):
    """One bounded text excerpt with a stable citation id."""

    model_config = ConfigDict(extra="forbid")

    passage_id: str
    text: str


class ResearchObservation(ToolObservation):
    """Tool observation plus research provenance, passages, and retrieval metadata."""

    model_config = ConfigDict(extra="ignore")

    requested_url: str
    evidence_id: str
    retrieval_outcome: RetrievalOutcome
    extraction_completeness: ExtractionCompleteness
    final_url: str | None = None
    publisher: str | None = None
    relationship: Relationship | None = None
    approved_scope: ApprovedResearchScope | None = None
    retrieved_at: datetime | None = None
    fresh: bool = True
    passages: list[ResearchPassage] = Field(default_factory=list)
    candidate_links: list[str] = Field(default_factory=list)


__all__ = [
    "ExtractionCompleteness",
    "ResearchObservation",
    "ResearchPassage",
    "RetrievalOutcome",
]
