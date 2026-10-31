"""Classify a finished digest run from its saved entries and connector warnings.

Warnings only exist for connectors that ran, and a connector that completed with
degradation still returns its remaining items, so no selected-source lookup is
needed here. Unknown codes stay benign: a future warning joins the failure set
explicitly instead of silently marking every digest partial.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from ai_news_agent.models import ConnectorWarning

CollectionOutcome = Literal["results", "no_eligible", "failed", "partial"]

# Codes emitted when the connector aborted that source's whole collect.
SOURCE_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "juya_rss_unavailable",
        "search_failed",
        "invalid_search_response",
        "no_input",
        "request_failed",
        "rate_limited",
        "auth_missing",
        "anti_bot_blocked",
        "proxy_connection_failed",
        "auth_required_missing",
        "auth_required_rejected",
    }
)


def collection_outcome(
    *, entry_count: int, warnings: Sequence[ConnectorWarning]
) -> CollectionOutcome:
    """Return how the run ended: entries, a clean empty collect, or a failure."""

    source_failed = any(
        warning.code in SOURCE_FAILURE_CODES for warning in warnings
    )
    if entry_count > 0:
        return "partial" if source_failed else "results"
    return "failed" if source_failed else "no_eligible"
