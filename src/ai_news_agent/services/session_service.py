"""Session use cases: CRUD, preferences, titles, and delete rules (8A.1 T7)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from ai_news_agent.digest_request_builder import resolve_digest_request
from ai_news_agent.repositories.session_store import SessionStore
from ai_news_agent.repositories.unit_of_work import SqliteUnitOfWork
from ai_news_agent.request import DigestRequest
from ai_news_agent.source_settings import SourceSettingsService
from ai_news_agent.telemetry import new_correlation_id
from ai_news_agent.services.session_records import (
    MessageRecord,
    SessionRecord,
    SessionRequestRecord,
    SessionRequestStats,
    initial_session_title,
)


class SessionBusyError(Exception):
    """A session-scoped operation was rejected because a request is active."""


class RequestInProgressError(Exception):
    """The same request ID is already active for this session."""


class RequestConflictError(Exception):
    """The same request ID was reused with a different submission."""


class _CancelRaceLost(Exception):
    """Internal signal: digest persistence committed before cancellation landed."""


CANCELLED_ASSISTANT_MESSAGE = "The request was cancelled."


def is_pending_juya_confirmation(record: SessionRequestRecord) -> bool:
    if record.status != "active" or record.run_id is not None:
        return False
    interpretation = record.interpretation or {}
    if interpretation.get("juya_confirmation_claimed"):
        return False
    return isinstance(interpretation.get("juya_confirmation"), dict)


class SessionService:
    """Session lifecycle use cases over :class:`SessionStore`."""

    def __init__(
        self,
        store: SessionStore,
        *,
        source_settings_service: SourceSettingsService | None = None,
    ) -> None:
        self._store = store
        self._source_settings = source_settings_service

    def create_session(self) -> SessionRecord:
        session_id = str(uuid.uuid4())
        self._store.create_session(session_id)
        record = self._store.get_session(session_id)
        assert record is not None
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._store.get_session(session_id)

    def list_sessions(self) -> list[SessionRecord]:
        return self._store.list_sessions()

    def get_session_request_stats(
        self,
        session_ids: list[str] | None = None,
    ) -> dict[str, SessionRequestStats]:
        return self._store.get_session_request_stats(session_ids)

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        return self._store.list_messages(session_id)

    def list_all_messages(self) -> list[MessageRecord]:
        return self._store.list_all_messages()

    def get_request(
        self,
        session_id: str,
        request_id: str,
    ) -> SessionRequestRecord | None:
        return self._store.get_request(session_id, request_id)

    def list_requests(self, session_id: str) -> list[SessionRequestRecord]:
        return self._store.list_requests(session_id)

    def set_request_interpretation(
        self,
        session_id: str,
        request_id: str,
        interpretation: dict[str, object] | None,
    ) -> None:
        if interpretation is None:
            self._store.set_request_interpretation(session_id, request_id, None)
            return
        existing = self._store.get_request(session_id, request_id)
        merged = dict(existing.interpretation or {}) if existing is not None else {}
        merged.update(interpretation)
        self._store.set_request_interpretation(session_id, request_id, merged)

    def claim_juya_confirmation(
        self,
        session_id: str,
        request_id: str,
    ) -> dict[str, object] | None:
        """Claim a pending Juya confirmation; only the first caller gets the payload."""
        return self._store.claim_juya_confirmation(session_id, request_id)

    def pending_clarification(self, session_id: str) -> dict[str, object] | None:
        """The newest succeeded request's pending question, if it has one."""
        for request in self._store.list_requests(session_id):
            if request.status != "succeeded":
                continue
            pending = (request.interpretation or {}).get("pending")
            return pending if isinstance(pending, dict) and pending else None
        return None

    def last_digest_request(self, session_id: str) -> dict[str, object] | None:
        """The stored request of the latest succeeded digest in this session."""
        for request in self._store.list_requests(session_id):
            if request.status != "succeeded" or request.run_id is None:
                continue
            stored = (request.interpretation or {}).get("request")
            return stored if isinstance(stored, dict) else None
        return None

    def stored_digest_request(
        self, session_id: str, user_message_id: int
    ) -> dict[str, object] | None:
        """The resolved digest request stored for one user message, if any."""
        for request in self._store.list_requests(session_id):
            if request.user_message_id != user_message_id:
                continue
            stored = (request.interpretation or {}).get("request")
            return stored if isinstance(stored, dict) else None
        return None

    def request_interpretations(self, session_id: str) -> dict[int, dict[str, object]]:
        """Public resolved-request metadata keyed by the user message it answers."""
        out: dict[int, dict[str, object]] = {}
        for request in reversed(self._store.list_requests(session_id)):
            public = (request.interpretation or {}).get("public")
            if isinstance(public, dict) and public:
                out[request.user_message_id] = public
        return out

    def juya_confirmation_projection(
        self, session_id: str
    ) -> dict[int, dict[str, object]]:
        """The pending confirmation, so a settled request stops asking."""
        out: dict[int, dict[str, object]] = {}
        for request in self._store.list_requests(session_id):
            if not is_pending_juya_confirmation(request):
                continue
            payload = (request.interpretation or {}).get("juya_confirmation")
            if not isinstance(payload, dict):
                continue
            out[request.user_message_id] = payload
            if request.assistant_message_id is not None:
                out[request.assistant_message_id] = payload
        return out

    def followup_projection(self, session_id: str) -> dict[int, dict[str, object]]:
        """Follow-up target and action keyed by user and assistant message ids."""
        out: dict[int, dict[str, object]] = {}
        for request in self._store.list_requests(session_id):
            followup = (request.interpretation or {}).get("followup")
            if not isinstance(followup, dict):
                continue
            digest_id = followup.get("digest_id")
            display_rank = followup.get("display_rank")
            action = followup.get("action")
            if digest_id is None or display_rank is None or action is None:
                continue
            payload = {
                "followup_target": {
                    "digest_id": int(digest_id),
                    "display_rank": int(display_rank),
                },
                "followup_action": str(action),
            }
            out[request.user_message_id] = payload
            if request.assistant_message_id is not None:
                out[request.assistant_message_id] = payload
        return out

    def rename_session(self, session_id: str, title: str) -> None:
        self._store.rename_session(session_id, title)

    def update_preferences(
        self,
        session_id: str,
        *,
        connector_names: list[str] | None,
        items_per_source: int | None,
    ) -> None:
        self._store.update_preferences(
            session_id,
            connector_names=connector_names,
            items_per_source=items_per_source,
        )

    def record_user_message(self, session_id: str, *, content: str) -> MessageRecord:
        self._store.insert_message(session_id, role="user", content=content)
        session = self._store.get_session(session_id)
        if session is not None and session.title is None:
            title = initial_session_title(content)
            if title is not None:
                self._store.rename_session(session_id, title)
        messages = self._store.list_messages(session_id)
        return messages[-1]

    def build_request(
        self,
        session_id: str,
        message: str,
        *,
        juya_item_mode: str | None = None,
    ) -> DigestRequest:
        """Compose a request where session preferences act only as defaults.

        Explicit message selectors win for this one request; the stored
        preference is never mutated.
        """
        session = self._store.get_session(session_id)
        if session is None:
            raise KeyError(f"session not found: {session_id}")
        req = resolve_digest_request(
            message,
            session_connector_names=session.connector_names,
        )
        if juya_item_mode is not None:
            req = replace(req, juya_item_mode=juya_item_mode)
        if self._source_settings is not None:
            req = self._source_settings.apply(req)
        return req

    def delete_session(self, session_id: str) -> None:
        """Delete an inactive session; reject deletion while a request is active."""
        active = [
            request
            for request in self._store.list_requests(session_id)
            if request.status == "active"
        ]
        if active:
            raise SessionBusyError(f"session {session_id} has an active request")
        self._store.delete_session(session_id)

    @staticmethod
    def _normalize_submission(
        *,
        content: str,
        juya_item_mode: str | None,
        followup_target: dict[str, object] | None,
        followup_action: str | None,
        repeat_of_user_message_id: int | None = None,
        replace_source: str | None = None,
    ) -> dict[str, object]:
        return {
            "content": content,
            "juya_item_mode": juya_item_mode if juya_item_mode is not None else "issue",
            "followup_target": followup_target,
            "followup_action": followup_action,
            "repeat_of_user_message_id": repeat_of_user_message_id,
            "replace_source": replace_source,
        }

    def _stored_submission(self, record: SessionRequestRecord) -> dict[str, object]:
        interpretation = record.interpretation or {}
        stored = interpretation.get("submission")
        if isinstance(stored, dict):
            # Rows written before repeat shipped carry no repeat keys; fill them
            # so an identical replay still matches.
            return {
                **stored,
                "repeat_of_user_message_id": stored.get(
                    "repeat_of_user_message_id"
                ),
                "replace_source": stored.get("replace_source"),
            }
        for message in self._store.list_messages(record.session_id):
            if message.id == record.user_message_id:
                return self._normalize_submission(
                    content=message.content,
                    juya_item_mode=None,
                    followup_target=None,
                    followup_action=None,
                )
        return self._normalize_submission(
            content="",
            juya_item_mode=None,
            followup_target=None,
            followup_action=None,
        )

    def begin_request(
        self,
        session_id: str,
        *,
        content: str,
        request_id: str | None = None,
        juya_item_mode: str | None = None,
        followup_target: dict[str, object] | None = None,
        followup_action: str | None = None,
        repeat_of_user_message_id: int | None = None,
        replace_source: str | None = None,
    ) -> SessionRequestRecord:
        if self._store.get_session(session_id) is None:
            raise KeyError(f"session not found: {session_id}")

        submission = self._normalize_submission(
            content=content,
            juya_item_mode=juya_item_mode,
            followup_target=followup_target,
            followup_action=followup_action,
            repeat_of_user_message_id=repeat_of_user_message_id,
            replace_source=replace_source,
        )

        if request_id is not None:
            existing = self._store.get_request(session_id, request_id)
            if existing is not None:
                if existing.status == "active":
                    raise RequestInProgressError(
                        f"request {request_id!r} is already active for session {session_id!r}"
                    )
                if self._stored_submission(existing) != submission:
                    raise RequestConflictError(
                        f"request {request_id!r} submission does not match for session {session_id!r}"
                    )
                return existing

        active_requests = [
            request
            for request in self._store.list_requests(session_id)
            if request.status == "active"
        ]
        pending_juya = [
            request
            for request in active_requests
            if is_pending_juya_confirmation(request)
        ]
        blocking = [
            request
            for request in active_requests
            if request not in pending_juya
        ]
        if blocking:
            raise SessionBusyError(f"session {session_id} has an active request")
        for pending in pending_juya:
            self.cancel_request(session_id, pending.id)

        resolved_id = request_id if request_id is not None else str(uuid.uuid4())
        message = self.record_user_message(session_id, content=content)
        self._store.create_request(
            session_id,
            resolved_id,
            user_message_id=message.id,
            correlation_id=new_correlation_id(),
        )
        record = self._store.get_request(session_id, resolved_id)
        assert record is not None
        self.set_request_interpretation(
            session_id,
            resolved_id,
            {"submission": submission},
        )
        record = self._store.get_request(session_id, resolved_id)
        assert record is not None
        return record

    def interrupt_active_requests(self) -> int:
        """Mark leftover active requests interrupted after startup or crash."""
        return self._store.interrupt_active_requests()

    def attach_interim_assistant(
        self,
        session_id: str,
        request_id: str,
        *,
        content: str,
    ) -> int:
        request = self._store.get_request(session_id, request_id)
        if request is None or request.status != "active":
            raise KeyError(
                f"active request not found: session={session_id!r} request={request_id!r}"
            )
        with SqliteUnitOfWork(self._store.db_path) as uow:
            assistant_message_id = uow.session_store.insert_message(
                session_id,
                role="assistant",
                content=content,
            )
            if not uow.session_store.set_assistant_message_if_active(
                session_id,
                request_id,
                assistant_message_id=assistant_message_id,
            ):
                raise KeyError(
                    f"active request not found: session={session_id!r} request={request_id!r}"
                )
        return assistant_message_id

    def cancel_request(self, session_id: str, request_id: str) -> bool:
        request = self._store.get_request(session_id, request_id)
        if (
            request is None
            or request.status != "active"
            or request.run_id is not None
        ):
            return False

        try:
            with SqliteUnitOfWork(self._store.db_path) as uow:
                assistant_message_id = uow.session_store.insert_message(
                    session_id,
                    role="assistant",
                    content=CANCELLED_ASSISTANT_MESSAGE,
                )
                if not uow.session_store.mark_cancelled_if_active(
                    session_id,
                    request_id,
                    assistant_message_id=assistant_message_id,
                ):
                    raise _CancelRaceLost
        except _CancelRaceLost:
            return False
        return True

    def complete_request(
        self,
        session_id: str,
        request_id: str,
        *,
        status: str,
        content: str,
        run_id: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> int:
        request = self._store.get_request(session_id, request_id)
        if request is None or request.status != "active":
            raise KeyError(
                f"active request not found: session={session_id!r} request={request_id!r}"
            )

        with SqliteUnitOfWork(self._store.db_path) as uow:
            assistant_message_id = uow.session_store.insert_message(
                session_id,
                role="assistant",
                content=content,
                run_id=run_id,
            )
            if not uow.session_store.mark_terminal_if_active(
                session_id,
                request_id,
                status=status,
                assistant_message_id=assistant_message_id,
                error_code=error_code,
                error_message=error_message,
            ):
                raise KeyError(
                    f"active request not found: session={session_id!r} request={request_id!r}"
                )
            if run_id is not None:
                uow.session_store.update_request_run_id(
                    session_id,
                    request_id,
                    run_id,
                )
        return assistant_message_id


__all__ = [
    "CANCELLED_ASSISTANT_MESSAGE",
    "RequestConflictError",
    "RequestInProgressError",
    "SessionBusyError",
    "SessionService",
]
