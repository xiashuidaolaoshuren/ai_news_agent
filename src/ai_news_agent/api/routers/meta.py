"""Meta routes: health and canonical source metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_news_agent.api.deps import get_application
from ai_news_agent.credential_health import summary_for_catalog_source
from ai_news_agent.services.composition import Application
from ai_news_agent.sources import DEFAULT_SOURCE_NAMES

_SOURCE_CATALOG_ORDER: tuple[str, ...] = (
    "juya",
    "huggingface",
    "github",
    "zhihu",
    "bilibili",
)

router = APIRouter()


@router.get("/health")
def health(application: Application = Depends(get_application)) -> dict[str, object]:
    return {"status": "ok", "fake": application.fake}


def _health_payload(summary) -> dict[str, object]:
    return {
        "current": summary.current,
        "stale": summary.stale,
        "credential_version": summary.credential_version,
        "observed_at": summary.observed_at,
        "kind": summary.kind,
    }


@router.get("/sources")
def sources(application: Application = Depends(get_application)) -> dict[str, object]:
    defaults = list(DEFAULT_SOURCE_NAMES)
    default_set = set(defaults)
    store = application.credential_health_store
    provider = application.credentials_service
    catalog: list[dict[str, object]] = []
    for name in _SOURCE_CATALOG_ORDER:
        health = summary_for_catalog_source(store, provider, name)
        catalog.append(
            {
                "name": name,
                "default": name in default_set,
                "opt_in": name not in default_set,
                "health": _health_payload(health),
            }
        )
    return {
        "defaults": defaults,
        "sources": catalog,
    }
