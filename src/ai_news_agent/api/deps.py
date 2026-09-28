"""FastAPI dependencies backed by the composition root."""

from __future__ import annotations

from fastapi import Request

from ai_news_agent.services.chat import ChatService
from ai_news_agent.services.composition import Application
from ai_news_agent.services.session_service import SessionService
from ai_news_agent.storage import DigestStore


def get_application(request: Request) -> Application:
    """Return the composition root stored on app state."""
    return request.app.state.application


def get_session_service(request: Request) -> SessionService:
    return get_application(request).session_service


def get_chat_service(request: Request) -> ChatService:
    return get_application(request).chat_service


def get_digest_store(request: Request) -> DigestStore:
    return get_application(request).digest_store
