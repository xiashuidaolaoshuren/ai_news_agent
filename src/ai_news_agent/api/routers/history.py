"""History HTTP routes: 7D.1 search and persist-only show (Milestone 8A.1 T16)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_news_agent.api.deps import get_application
from ai_news_agent.api.schemas.history import (
    HistoricalItemRefOut,
    HistoryItemShowOut,
    HistorySearchMatchOut,
    HistorySearchResultOut,
)
from ai_news_agent.history import (
    HistorySearchQuery,
    format_historical_item_ref,
    parse_historical_item_ref,
)
from ai_news_agent.history_search import (
    project_historical_entry,
    search_digest_history,
    show_historical_item,
)
from ai_news_agent.services.composition import Application
from ai_news_agent.sources import parse_sources_csv

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/search", response_model=HistorySearchResultOut)
def search_history(
    text: str | None = Query(default=None),
    sources: str | None = Query(default=None),
    topics: str | None = Query(default=None),
    since: date | None = Query(default=None),
    until: date | None = Query(default=None),
    limit: int = Query(default=10),
    application: Application = Depends(get_application),
) -> HistorySearchResultOut:
    query: HistorySearchQuery
    try:
        query = HistorySearchQuery(
            text=text,
            sources=parse_sources_csv(sources) if sources else None,
            topics=_split_csv(topics) if topics else None,
            since=since,
            until=until,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = search_digest_history(application.digest_store, query)
    return HistorySearchResultOut(
        matches=[
            HistorySearchMatchOut(
                ref=HistoricalItemRefOut(
                    token=format_historical_item_ref(match.ref),
                    digest_id=match.ref.digest_id,
                    run_id=match.ref.run_id,
                    entry_id=match.ref.entry_id,
                    rank=match.ref.rank,
                ),
                generated_at=match.generated_at,
                source_kind=match.source_kind,
                title=match.title,
                url=match.url,
                excerpt=match.excerpt,
                score=match.score,
            )
            for match in result.matches
        ],
        scanned_count=result.scanned_count,
        archive_truncated=result.archive_truncated,
        caveats=result.caveats,
    )


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return parts or None


@router.get("/{historical_item_ref}", response_model=HistoryItemShowOut)
def show_history(
    historical_item_ref: str,
    application: Application = Depends(get_application),
) -> HistoryItemShowOut:
    try:
        parse_historical_item_ref(historical_item_ref)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    markdown = show_historical_item(application.digest_store, historical_item_ref)
    if markdown is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="historical item not found",
        )
    entry_payload = project_historical_entry(application.digest_store, historical_item_ref)
    return HistoryItemShowOut(
        token=historical_item_ref,
        markdown=markdown,
        entry=entry_payload,
    )