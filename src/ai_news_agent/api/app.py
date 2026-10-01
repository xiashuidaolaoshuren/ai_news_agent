"""FastAPI application factory (Milestone 8A.1 T13)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_news_agent.api.routers import history, meta, openclaw, sessions
from ai_news_agent.services.composition import Application

_LOOPBACK_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    application: Application = app.state.application
    application.session_service.interrupt_active_requests()
    yield


def _register_streaming_openapi_components(app: FastAPI) -> None:
    from ai_news_agent.api.schemas import streaming as streaming_schemas

    streaming_models = (
        streaming_schemas.StartedPayload,
        streaming_schemas.ProgressPayload,
        streaming_schemas.DeltaPayload,
        streaming_schemas.WorkflowErrorPayload,
        streaming_schemas.DigestPayload,
        streaming_schemas.DonePayload,
        streaming_schemas.ErrorPayload,
        streaming_schemas.StartedStreamEvent,
        streaming_schemas.ProgressStreamEvent,
        streaming_schemas.DeltaStreamEvent,
        streaming_schemas.DigestStreamEvent,
        streaming_schemas.DoneStreamEvent,
        streaming_schemas.ErrorStreamEvent,
    )

    def openapi() -> dict[str, object]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in streaming_models:
            components[model.__name__] = model.model_json_schema(
                ref_template="#/components/schemas/{model}",
            )
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(application: Application) -> FastAPI:
    """Build the FastAPI app with loopback CORS and mounted routers."""
    app = FastAPI(lifespan=_lifespan)
    app.state.application = application

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        detail = "Invalid request body"
        for error in exc.errors():
            if error.get("type") == "extra_forbidden":
                detail = "Invalid request body"
                break
            message = error.get("msg")
            if isinstance(message, str) and message:
                detail = message
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": detail},
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOOPBACK_CORS_ORIGINS),
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )
    app.include_router(meta.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(history.router, prefix="/api/v1")
    app.include_router(openclaw.router)
    _register_streaming_openapi_components(app)
    return app
