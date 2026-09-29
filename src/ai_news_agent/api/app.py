"""FastAPI application factory (Milestone 8A.1 T13)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_news_agent.api.routers import history, meta, sessions
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


def create_app(application: Application) -> FastAPI:
    """Build the FastAPI app with loopback CORS and mounted routers."""
    app = FastAPI(lifespan=_lifespan)
    app.state.application = application
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOOPBACK_CORS_ORIGINS),
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )
    app.include_router(meta.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(history.router, prefix="/api/v1")
    return app
