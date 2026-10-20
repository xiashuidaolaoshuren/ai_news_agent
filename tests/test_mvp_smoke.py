"""Milestone 1 acceptance smoke tests (Task T14).

Fast, deterministic checks that mirror the offline CLI UX without live APIs.
"""

from __future__ import annotations

import io
from pathlib import Path

from ai_news_agent.cli import (
    main as cli_main,
)


def test_mvp_smoke_cli_fake_digest(tmp_path: Path) -> None:
    buf = io.StringIO()
    code = cli_main(
        [
            "digest",
            "--fake",
            "--db-path",
            str(tmp_path / "mvp_cli.db"),
            "--sources",
            "github,bilibili",
            "--topics",
            "RAG",
        ],
        stdout=buf,
    )
    out = buf.getvalue()
    assert code == 0
    assert "AI News Digest" in out
    assert "Fake GitHub repo" in out
