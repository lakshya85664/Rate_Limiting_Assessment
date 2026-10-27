
import json
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "query",
    "prompt",
    "email",
    "principal_id",
}


def redact(value: Any) -> Any:
    """Recursively redact sensitive values before writing trace data."""
    if isinstance(value, dict):
        redacted = {}

        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item)

        return redacted

    if isinstance(value, list):
        return [redact(item) for item in value]

    if isinstance(value, tuple):
        return [redact(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return f"<{type(value).__name__}>"


class JsonlTraceWriter:
    """Append structured, redacted JSON events to a JSONL file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def write(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise TypeError("event must be a dictionary")

        safe_event = redact(event)
        line = json.dumps(
            safe_event,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )

        with self._lock:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")


class ReliabilityMetrics:
    """Thread-safe counters for tool execution outcomes."""

    def __init__(self):
        self._counts: Counter[str] = Counter()
        self._lock = Lock()

    def record(self, status: str, *, attempts: int = 1) -> None:
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")

        if (
            not isinstance(attempts, int)
            or isinstance(attempts, bool)
            or attempts < 0
        ):
            raise ValueError("attempts must be a non-negative integer")

        with self._lock:
            self._counts[f"status.{status}"] += 1
            self._counts["requests.total"] += 1
            self._counts["provider.attempts"] += attempts

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counts.items()))
