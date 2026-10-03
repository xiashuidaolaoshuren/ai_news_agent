"""Collection node factory for digest workflow (T10b)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from ai_news_agent.connectors.base import ConnectorRequest, ConnectorResult, SourceConnector
from ai_news_agent.graph.state import DigestGraphState, WorkflowError
from ai_news_agent.sources import resolve_connector_names
from ai_news_agent.progress import emit_progress

logger = logging.getLogger(__name__)


def _format_connector_call_start(name: str) -> str:
    return f"Calling {name}…"


def _format_connector_call_done(name: str, item_count: int) -> str:
    suffix = "result" if item_count == 1 else "results"
    return f"Done {name}: Found {item_count} {name} {suffix}."


def _format_connector_call_failed(name: str) -> str:
    return f"Tool failed {name}: collection failed."


def make_collect_sources_node(
    connectors: Sequence[SourceConnector],
    *,
    on_progress: Callable[[str], None] | None = None,
):
    def _report(line: str) -> None:
        if on_progress is not None:
            on_progress(line)
        emit_progress(line)

    async def _collect_connector(
        connector: SourceConnector,
        request: ConnectorRequest,
    ) -> tuple[SourceConnector, ConnectorResult | None, Exception | None]:
        name = connector.name()
        try:
            result = await connector.collect(request)
            if isinstance(result, ConnectorResult):
                _report(_format_connector_call_done(name, len(result.items)))
                return connector, result, None
            if isinstance(result, Exception):
                logger.exception("%s collect returned exception", name)
                _report(_format_connector_call_failed(name))
                return connector, None, result
            raise TypeError(f"{name} collect returned unexpected type")
        except Exception as exc:
            logger.exception("%s collect failed", name)
            _report(_format_connector_call_failed(name))
            return connector, None, exc

    async def collect_sources_node(state: DigestGraphState) -> dict[str, object]:
        request = state.get("connector_request")
        if request is None:
            return {
                "errors": [
                    WorkflowError(
                        stage="collect", message="missing ConnectorRequest in state"
                    )
                ]
            }

        digest_request = state.get("request")
        if digest_request is not None:
            allowed_names = resolve_connector_names(digest_request.connector_names)
        else:
            allowed_names = resolve_connector_names(None)
        allowed = set(allowed_names)
        selected = [c for c in connectors if c.name() in allowed]
        if not selected:
            return {
                "errors": [
                    WorkflowError(
                        stage="collect",
                        message="no matching connectors",
                        detail=", ".join(allowed_names),
                    )
                ]
            }

        _report("Collecting from sources…")

        for connector in selected:
            _report(_format_connector_call_start(connector.name()))

        results = await asyncio.gather(
            *[_collect_connector(connector, request) for connector in selected]
        )
        items = []
        warnings = []
        errors = []
        for connector, result, error in results:
            if result is not None:
                items.extend(result.items)
                warnings.extend(result.warnings)
                continue
            if error is not None:
                errors.append(
                    WorkflowError(
                        stage="collect",
                        message=f"{connector.name()} raised {type(error).__name__}",
                        detail=str(error),
                    )
                )
        out: dict[str, object] = {}
        if items:
            out["collected_items"] = items
        if warnings:
            out["warnings"] = warnings
        if errors:
            out["errors"] = errors
        return out

    return collect_sources_node
