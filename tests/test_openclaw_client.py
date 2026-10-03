"""Tests for OpenClaw thin client that calls the local digest service."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from ai_news_agent.adapters.openclaw_client import request_digest_markdown
from _service_server import UvicornTestServer


@pytest.fixture
def service_url(tmp_path: Path) -> str:
    server = UvicornTestServer(fake=True, db_path=tmp_path / "client.db").start()
    yield server.url
    server.stop()


def test_request_digest_markdown_returns_text(service_url: str) -> None:
    text = request_digest_markdown(
        service_url,
        timeframe_hint="today",
        sources_hint="github",
        fake=True,
        correlation_id="client-test-1",
    )
    assert "AI News Digest" in text
    assert "Fake GitHub repo" in text


def test_openclaw_client_cli_prints_stdout(
    service_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_NEWS_AGENT_SERVICE_URL", service_url)
    from ai_news_agent.adapters.openclaw_client import main as client_main

    buf = StringIO()
    code = client_main(
        [
            "--timeframe",
            "today",
            "--sources",
            "github",
            "--fake",
        ],
        stdout=buf,
    )
    assert code == 0
    assert "Fake GitHub repo" in buf.getvalue()
