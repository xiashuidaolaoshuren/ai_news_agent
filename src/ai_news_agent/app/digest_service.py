"""Persistent local HTTP service entry point (FastAPI on ``ai-news-agent service``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

import uvicorn

from ai_news_agent.env import configure_bilibili_network_from_env, load_local_env
from ai_news_agent.logging_setup import configure_logging, get_logger

logger = get_logger("digest_service")

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    """CLI entry: ``python -m ai_news_agent.app.digest_service`` or ``ai-news-agent service``."""
    del stdout
    load_local_env()
    configure_bilibili_network_from_env(logger)
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="ai-news-agent service",
        description="Run the persistent local digest HTTP service.",
    )
    parser.add_argument("--host", default=_DEFAULT_HOST, help="Bind host (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help=f"Bind port (default: {_DEFAULT_PORT})",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path.cwd() / "digest.sqlite",
        help="SQLite path for DigestStore",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help=(
            "Offline deterministic mode (no network, no OpenAI key). "
            "Writes go to a temporary database copy; --db-path is left unchanged."
        ),
    )

    ns = parser.parse_args(argv if argv is not None else sys.argv[1:])

    from ai_news_agent.api.app import create_app
    from ai_news_agent.app.fake_runtime_db import materialize_fake_db, remove_fake_runtime_db
    from ai_news_agent.services.composition import build_application

    runtime_db: Path | None = None
    db_path = ns.db_path
    if ns.fake:
        runtime_db = materialize_fake_db(ns.db_path)
        db_path = runtime_db

    try:
        application = build_application(fake=ns.fake, db_path=db_path)
        app = create_app(application)
        logger.info(
            "digest service listening on http://%s:%s fake=%s db_path=%s",
            ns.host,
            ns.port,
            ns.fake,
            db_path,
        )
        uvicorn.run(app, host=ns.host, port=ns.port)
    finally:
        if runtime_db is not None:
            remove_fake_runtime_db(runtime_db)
    return 0


__all__ = ["main"]
