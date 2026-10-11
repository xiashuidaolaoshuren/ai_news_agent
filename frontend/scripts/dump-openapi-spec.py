"""Dump OpenAPI schema from the fake-mode FastAPI app (offline, no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from ai_news_agent.api.app import create_app
from ai_news_agent.services.composition import build_application


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "openapi.json"
    db_path = out.parent / ".openapi-dump.sqlite"
    if db_path.exists():
        db_path.unlink()
    application = build_application(fake=True, db_path=db_path)
    client = TestClient(create_app(application))
    schema = client.get("/openapi.json").json()
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
