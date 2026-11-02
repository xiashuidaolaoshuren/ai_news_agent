"""Settings routes for source profiles (B6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ai_news_agent.api.deps import get_source_settings_service
from ai_news_agent.api.schemas.settings import (
    LanguageOut,
    LanguageUpdateIn,
    SourceProfileListOut,
)
from ai_news_agent.source_settings import (
    SourceSettingsService,
    SourceSettingsValidationError,
    UnknownSourceError,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/language", response_model=LanguageOut)
def get_output_language(
    service: SourceSettingsService = Depends(get_source_settings_service),
) -> dict[str, str]:
    return {"language": service.get_language()}


@router.put("/language", response_model=LanguageOut)
def save_output_language(
    body: LanguageUpdateIn,
    service: SourceSettingsService = Depends(get_source_settings_service),
) -> dict[str, str]:
    try:
        language = service.save_language(body.language)
    except SourceSettingsValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    return {"language": language}


@router.get("/sources", response_model=SourceProfileListOut)
def list_source_profiles(
    service: SourceSettingsService = Depends(get_source_settings_service),
) -> dict[str, Any]:
    return {"sources": service.list_profiles()}


@router.put("/sources/{name}")
def save_source_profile(
    name: str,
    body: dict[str, Any],
    service: SourceSettingsService = Depends(get_source_settings_service),
) -> dict[str, Any]:
    try:
        return service.save_profile(name, body)
    except UnknownSourceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SourceSettingsValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
