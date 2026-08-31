"""Redacted JSONL request events for the disposable pilot."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlLogger:
    """Write one bounded, lock-protected event per line without payload data."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: Mapping[str, Any]) -> None:
        safe_event = {
            "timestamp": str(event.get("timestamp", _utc_now())),
            "request_id": str(event.get("request_id", "unknown")),
            "method": str(event.get("method", "unknown")),
            "route": str(event.get("route", "unknown")),
            "status": int(event.get("status", 500)),
            "outcome": str(event.get("outcome", "failure")),
            "failure_class": event.get("failure_class"),
            "duration_ms": float(event.get("duration_ms", 0.0)),
            "actor_present": bool(event.get("actor_present", False)),
            "idempotency_present": bool(event.get("idempotency_present", False)),
        }
        encoded = json.dumps(
            safe_event,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.write("\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
