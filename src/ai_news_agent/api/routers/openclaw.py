"""OpenClaw compatibility routes: unversioned /health, /digest, /followup (8A.1 T17)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ai_news_agent.api.deps import get_application
from ai_news_agent.app.digest_service import digest_request_from_json
from ai_news_agent.services.composition import Application
from ai_news_agent.telemetry import new_correlation_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openclaw"])

_SAFE_SERVICE_ERROR = "Request failed."


@router.get("/health")
def health(application: Application = Depends(get_application)) -> dict[str, Any]:
    return {"status": "ok", "fake": application.fake}


async def _json_body(request: Request) -> dict[str, Any] | None:
    raw = await request.body()
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


@router.post("/digest")
async def digest(
    request: Request,
    application: Application = Depends(get_application),
) -> JSONResponse:
    runtime = application.openclaw_runtime
    body = await _json_body(request)
    if body is None:
        return JSONResponse(status_code=400, content={"error": "invalid JSON body"})

    correlation_id = str(body.get("correlation_id") or new_correlation_id())
    use_fake = bool(body.get("fake", runtime.fake))
    if use_fake != runtime.fake:
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    f"service fake={runtime.fake} but request fake={use_fake}; "
                    "restart service with matching mode"
                ),
            },
        )

    try:
        digest_request = digest_request_from_json(body)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    message = str(body.get("message") or "").strip()
    try:
        result, stages, elapsed = await runtime.run_digest(
            digest_request,
            correlation_id=correlation_id,
            message=message,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - compatibility error surface
        logger.exception("digest_service failed correlation_id=%s", correlation_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": _SAFE_SERVICE_ERROR,
                "correlation_id": correlation_id,
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "text": result.text,
            "run_id": result.run_id,
            "correlation_id": correlation_id,
            "elapsed_s": round(elapsed, 3),
            "stages": stages,
        },
    )


@router.post("/followup")
async def followup(
    request: Request,
    application: Application = Depends(get_application),
) -> JSONResponse:
    runtime = application.openclaw_runtime
    body = await _json_body(request)
    if body is None:
        return JSONResponse(status_code=400, content={"error": "invalid JSON body"})

    message = body.get("message")
    if message is None or not str(message).strip():
        return JSONResponse(
            status_code=400,
            content={"error": "message is required"},
        )

    correlation_id = str(body.get("correlation_id") or new_correlation_id())
    try:
        outcome = await runtime.run_followup(
            message=str(message).strip(),
            correlation_id=correlation_id,
        )
    except Exception as exc:  # noqa: BLE001 - compatibility error surface
        logger.exception("followup_service failed correlation_id=%s", correlation_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": _SAFE_SERVICE_ERROR,
                "correlation_id": correlation_id,
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "text": outcome["text"],
            "run_id": outcome["run_id"],
            "path": outcome["path"],
            "correlation_id": correlation_id,
        },
    )