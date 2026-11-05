"""Settings routes for source profiles (B6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ai_news_agent.access import llm_url_guard, validate_llm_base_url
from ai_news_agent.api.deps import (
    get_application,
    get_credentials_provider,
    get_source_settings_service,
)
from ai_news_agent.api.schemas.settings import (
    CredentialTestOut,
    CredentialUpdateIn,
    CredentialsOut,
    LanguageOut,
    LanguageUpdateIn,
    LlmCredentialUpdateIn,
    SourceProfileListOut,
)
from ai_news_agent.credential_health import credential_name_to_source, health_version_for_source
from ai_news_agent.credential_tests import (
    TESTABLE_CREDENTIAL_NAMES,
    UnconfiguredCredentialError,
    UnreadableCredentialError,
    run_credential_test,
)
from ai_news_agent.services.composition import Application
from ai_news_agent.credentials import (
    CREDENTIAL_ENV_NAMES,
    CredentialsProvider,
    MissingSecretKeyError,
    UnknownCredentialNameError,
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


@router.get("/credentials", response_model=CredentialsOut)
def list_credentials(
    provider: CredentialsProvider = Depends(get_credentials_provider),
) -> dict[str, Any]:
    rows = provider.statuses()
    return {
        "secret_key_configured": provider.has_secret_key(),
        "credentials": [
            {
                "name": row.name,
                "status": row.status,
                "last4": row.last4,
                "version": row.version,
            }
            for row in rows
        ],
    }


@router.put("/credentials/llm", response_model=CredentialsOut)
def save_llm_credentials(
    body: LlmCredentialUpdateIn,
    provider: CredentialsProvider = Depends(get_credentials_provider),
    application: Application = Depends(get_application),
) -> dict[str, Any]:
    if body.base_url and application.access.remote:
        try:
            validate_llm_base_url(
                body.base_url, allow_local=application.access.allow_local_llm
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        provider.save_llm(
            api_key=body.api_key,
            base_url=body.base_url,
            model=body.model,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except MissingSecretKeyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return list_credentials(provider=provider)


@router.delete("/credentials/llm", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_credentials(
    provider: CredentialsProvider = Depends(get_credentials_provider),
) -> None:
    provider.delete_llm()


@router.post("/credentials/{name}/test", response_model=CredentialTestOut)
async def test_credential(
    name: str,
    application: Application = Depends(get_application),
) -> dict[str, str]:
    if name.startswith("BILIBILI_"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Bilibili credential test is not supported",
        )
    if name not in TESTABLE_CREDENTIAL_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown credential")
    provider = application.credentials_service
    health_store = application.credential_health_store
    try:
        outcome = await run_credential_test(
            name, provider, guard=llm_url_guard(application.access)
        )
    except UnconfiguredCredentialError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnreadableCredentialError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    source = credential_name_to_source(name)
    if source is not None:
        version = health_version_for_source(provider, source)
        health_store.record(
            source=source,
            credential_version=version,
            kind="test",
            result=outcome.result,
        )
    return {"name": name, "result": outcome.result, "reason": outcome.reason}


@router.put("/credentials/{name}", response_model=CredentialsOut)
def save_credential(
    name: str,
    body: CredentialUpdateIn,
    provider: CredentialsProvider = Depends(get_credentials_provider),
) -> dict[str, Any]:
    if name == "llm":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown credential")
    if name not in CREDENTIAL_ENV_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown credential")
    try:
        provider.save(name, body.value)
    except MissingSecretKeyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnknownCredentialNameError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return list_credentials(provider=provider)


@router.delete("/credentials/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    name: str,
    provider: CredentialsProvider = Depends(get_credentials_provider),
) -> None:
    if name == "llm":
        provider.delete_llm()
        return
    if name not in CREDENTIAL_ENV_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown credential")
    try:
        provider.delete(name)
    except UnknownCredentialNameError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
