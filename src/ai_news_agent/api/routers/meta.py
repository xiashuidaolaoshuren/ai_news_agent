"""Meta routes: health and canonical source metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_news_agent.api.deps import get_application
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


@router.get("/sources")
def sources() -> dict[str, object]:
    defaults = list(DEFAULT_SOURCE_NAMES)
    default_set = set(defaults)
    return {
        "defaults": defaults,
        "sources": [
            {
                "name": name,
                "default": name in default_set,
                "opt_in": name not in default_set,
            }
            for name in _SOURCE_CATALOG_ORDER
        ],
    }
