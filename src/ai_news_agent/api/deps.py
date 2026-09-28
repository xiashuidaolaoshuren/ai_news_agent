"""FastAPI dependencies backed by the composition root."""

from __future__ import annotations

from fastapi import Request

from ai_news_agent.services.composition import Application


def get_application(request: Request) -> Application:
    """Return the composition root stored on app state."""
    return request.app.state.application
