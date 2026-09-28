"""Server-Sent Events frame encoding (Milestone 8A.1 T14)."""

from __future__ import annotations

import json
from typing import Any


def encode_sse(event: str, payload: dict[str, Any]) -> str:
    """Encode one SSE frame with JSON payload."""
    data = json.dumps(payload, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {data}\n\n"
