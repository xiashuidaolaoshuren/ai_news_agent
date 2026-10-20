"""Temporary SQLite copy for fake-mode service runs so demo files stay unchanged."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from ai_news_agent.logging_setup import get_logger

logger = get_logger("fake_runtime_db")

_FAKE_DB_PREFIX = "anra-fake-"
_FAKE_DB_SUFFIX = ".sqlite"


def materialize_fake_db(source: Path) -> Path:
    """Return a temp database path: backup of *source* when it exists, else an empty file."""
    fd, raw_path = tempfile.mkstemp(prefix=_FAKE_DB_PREFIX, suffix=_FAKE_DB_SUFFIX)
    runtime = Path(raw_path)
    # mkstemp leaves an empty file open; close the handle before SQLite uses the path.
    os.close(fd)

    if source.is_file():
        with sqlite3.connect(source) as src_conn, sqlite3.connect(runtime) as dst_conn:
            src_conn.backup(dst_conn)
        logger.info(
            "fake mode using temporary database copy; source %s is not modified",
            source,
        )
    else:
        logger.info(
            "fake mode using new temporary database; source %s was not created",
            source,
        )

    return runtime


def remove_fake_runtime_db(runtime: Path) -> None:
    """Remove a fake runtime database and any SQLite sidecar files next to it."""
    for path in (runtime, Path(f"{runtime}-wal"), Path(f"{runtime}-shm")):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("failed to remove fake runtime file %s", path, exc_info=True)


__all__ = ["materialize_fake_db", "remove_fake_runtime_db"]
