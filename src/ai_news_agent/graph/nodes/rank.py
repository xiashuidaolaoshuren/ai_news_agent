"""Ranking node for digest workflow (T10c)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ai_news_agent.graph.state import DigestGraphState, WorkflowError
from ai_news_agent.models import ConnectorWarning, utcnow
from ai_news_agent.ranking import rank_items, within_timeframe


def make_rank_items_node(*, now_provider: Callable[[], datetime] | None = None):
    """Build a node that runs :func:`~ai_news_agent.ranking.rank_items` on collected items."""

    def rank_items_node(state: DigestGraphState) -> dict[str, object]:
        req = state.get("request")
        if req is None:
            return {
                "errors": [
                    WorkflowError(
                        stage="rank", message="missing DigestRequest in state"
                    )
                ]
            }
        items = state.get("collected_items") or []
        if not items:
            return {"ranked_items": []}
        warnings = []
        if req.strict_timeframe and req.timeframe:
            reference = now_provider() if now_provider is not None else utcnow()
            kept = sum(
                1 for item in items if within_timeframe(item, req.timeframe, reference)
            )
            dropped = len(items) - kept
            if dropped:
                warnings.append(
                    ConnectorWarning(
                        connector="digest",
                        code="timeframe_excluded_items",
                        message=(
                            f"{dropped} collected item(s) fell outside "
                            f"{req.timeframe} and were excluded"
                        ),
                    )
                )
        kwargs: dict[str, object] = {
            "top_n": req.top_n,
            "timeframe": req.timeframe,
            "items_per_source": req.items_per_source,
            "strict_timeframe": req.strict_timeframe,
        }
        if now_provider is not None:
            kwargs["now"] = now_provider()
        ranked = rank_items(items, **kwargs)  # type: ignore[arg-type]
        out: dict[str, object] = {"ranked_items": ranked}
        if warnings:
            out["warnings"] = warnings
        return out

    return rank_items_node
