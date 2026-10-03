"""Local Gradio chat UI delegating to :class:`~ai_news_agent.chat.ChatService` (Task T13)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import gradio as gr

from ai_news_agent.chat import ChatService
from ai_news_agent.env import (
    configure_bilibili_network_from_env,
    load_local_env,
    log_bilibili_env_diagnostics,
)
from ai_news_agent.logging_setup import configure_logging, get_logger
from ai_news_agent.sources import DEFAULT_SOURCE_NAMES

_UI_ERROR_MESSAGE = (
    "Something went wrong while processing your request. "
    "Please check the terminal or log file for details and try again."
)

_SOURCE_TOGGLE_CHOICES: tuple[str, ...] = (
    "juya",
    "huggingface",
    "github",
    "zhihu",
    "bilibili",
)

_EMPTY_SOURCES_MESSAGE = (
    "Please enable at least one source (Juya, Hugging Face, GitHub, Zhihu, or Bilibili)."
)

_DEFAULT_ITEMS_PER_SOURCE = 5
_MAX_ITEMS_PER_SOURCE = 20
_INVALID_ITEMS_PER_SOURCE_MESSAGE = (
    f"Items per source must be a whole number from 1 to {_MAX_ITEMS_PER_SOURCE}."
)

_EXAMPLE_ROWS: list[list] = [
    ["Give me today's AI digest", ["juya"]],
    ["Digest https://daily.juya.uk/", ["juya"]],
    ["Give me today's AI digest from github only", ["github"]],
    ["Digest https://github.com/langchain-ai/langgraph", ["github"]],
    ["Digest bilibili channel 285286947", ["bilibili"]],
    ["Show Hugging Face trending models", ["huggingface"]],
    ["Find Zhihu practitioner insights on RAG", ["zhihu"]],
    ["follow up on item 1", ["juya"]],
    [
        "search history for RAG agents from huggingface,zhihu since 2026-08-01",
        ["huggingface", "zhihu"],
    ],
    ["open history d12:r3", ["juya"]],
]

logger = get_logger("gradio")


def _coerce_items_per_source(raw: object) -> int | None:
    """Return validated session N, or ``None`` when the UI value is invalid."""
    if raw is None or raw == "":
        return _DEFAULT_ITEMS_PER_SOURCE
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 1 or value > _MAX_ITEMS_PER_SOURCE:
        return None
    return value


def _build_service(*, fake: bool, db_path: Path) -> ChatService:
    """Build the Gradio chat service from the shared composition root."""
    from ai_news_agent.services import composition

    return composition.build_application(fake=fake, db_path=db_path).chat_service


def create_app(service: ChatService) -> gr.Blocks:
    """Build a Gradio chat UI with session-sticky source toggles and streaming."""

    async def respond_stream(
        message: str,
        _history: list,
        enabled_sources: list[str],
        items_per_source: object,
    ) -> AsyncIterator[str]:
        if not enabled_sources:
            yield _EMPTY_SOURCES_MESSAGE
            return
        session_n = _coerce_items_per_source(items_per_source)
        if session_n is None:
            yield _INVALID_ITEMS_PER_SOURCE_MESSAGE
            return
        try:
            async for partial in service.handle_message_streaming_async(
                message,
                session_connector_names=enabled_sources,
                session_items_per_source=session_n,
            ):
                yield partial
        except Exception:
            logger.exception("gradio request failed")
            yield _UI_ERROR_MESSAGE

    with gr.Blocks(title="AI News Research Agent") as demo:
        gr.Markdown(
            "# AI News Research Agent\n"
            "Ask for an AI news digest (e.g. mention \"digest\"). Juya is the default bulletin; "
            "enable Hugging Face, GitHub, Zhihu, or Bilibili for opt-in model, repo, practitioner, "
            "or video discovery. Include GitHub repo URLs, Bilibili video URLs, channel hints, "
            "or `daily.juya.uk` issue links for targeted runs. "
            'Follow up with "show sources", ranking hints, or "show caveats".'
        )
        source_toggles = gr.CheckboxGroup(
            choices=list(_SOURCE_TOGGLE_CHOICES),
            value=list(DEFAULT_SOURCE_NAMES),
            label="Sources",
            info=(
                "Session filters for digest runs. Juya is selected by default; override one "
                "request with phrases like 'huggingface only', 'github only', 'zhihu only', "
                "'bilibili only', or a Juya issue URL."
            ),
        )
        items_per_source_input = gr.Number(
            value=_DEFAULT_ITEMS_PER_SOURCE,
            minimum=1,
            maximum=_MAX_ITEMS_PER_SOURCE,
            precision=0,
            label="Items per source",
            info=(
                "Up to this many ranked items from each checked source; empty sources are "
                "omitted. Default 5."
            ),
        )
        chat = gr.ChatInterface(
            fn=respond_stream,
            additional_inputs=[source_toggles, items_per_source_input],
            examples=None,
        )
        with gr.Accordion("Example prompts", open=False):
            gr.Examples(
                examples=_EXAMPLE_ROWS,
                inputs=[chat.textbox, source_toggles],
                outputs=chat.chatbot,
                fn=respond_stream,
                cache_examples=False,
            )

    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ai_news_agent.app.gradio_app",
        description="Launch the AI News Research Agent Gradio chat UI.",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Offline deterministic mode (fake connectors and summarizer; no API keys).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path.cwd() / "digest.sqlite",
        help="SQLite path for DigestStore (default: ./digest.sqlite in cwd)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="HTTP port for the local server (default: 7860)",
    )

    ns = parser.parse_args(argv if argv is not None else sys.argv[1:])

    load_local_env()
    configure_logging()
    logger.info(
        "starting gradio fake=%s db_path=%s port=%s",
        ns.fake,
        ns.db_path,
        ns.port,
    )
    if not ns.fake:
        log_bilibili_env_diagnostics(logger)
        configure_bilibili_network_from_env(logger)

    try:
        service = _build_service(fake=ns.fake, db_path=ns.db_path)
    except ValueError as e:
        logger.exception("failed to build service")
        print(str(e), file=sys.stderr)
        return 2

    demo = create_app(service)
    logger.info("gradio launch on port=%s", ns.port)
    demo.launch(server_port=ns.port)
    return 0


__all__ = ["create_app", "main", "_UI_ERROR_MESSAGE"]

if __name__ == "__main__":
    raise SystemExit(main())
