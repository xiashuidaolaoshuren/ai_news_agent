"""Test helper: run the FastAPI app under uvicorn on an ephemeral port."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any


class UvicornTestServer:
    """Real-socket FastAPI server for client tests that need HTTP, not TestClient."""

    def __init__(
        self,
        *,
        fake: bool,
        db_path: Path,
        interface_router: Any | None = None,
    ) -> None:
        import uvicorn

        from ai_news_agent.api.app import create_app
        from ai_news_agent.services.composition import build_application

        self.application = build_application(fake=fake, db_path=db_path)
        if interface_router is not None:
            self.application.openclaw_runtime._interface_router = interface_router
        self._server = uvicorn.Server(
            uvicorn.Config(
                create_app(self.application),
                host="127.0.0.1",
                port=0,
                log_level="warning",
            )
        )
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        for server in self._server.servers:
            for sock in server.sockets:
                return int(sock.getsockname()[1])
        raise RuntimeError("uvicorn test server is not started")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "UvicornTestServer":
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 15.0
        while not self._server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        if not self._server.started:
            raise RuntimeError("uvicorn test server did not start")
        return self

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=15.0)
            self._thread = None