
import json

import pytest

from reliability.observability import (
    JsonlTraceWriter,
    ReliabilityMetrics,
    redact,
)


def test_redact_removes_sensitive_fields_recursively():
    payload = {
        "principal_id": "user-123",
        "query": "private search query",
        "metadata": {
            "api_key": "secret-key",
            "status": "ok",
        },
    }

    result = redact(payload)

    assert result["principal_id"] == "[REDACTED]"
    assert result["query"] == "[REDACTED]"
    assert result["metadata"]["api_key"] == "[REDACTED]"
    assert result["metadata"]["status"] == "ok"


def test_redact_handles_lists_and_tuples():
    result = redact(
        [
            {"password": "secret"},
            ({"token": "abc"}, "safe"),
        ]
    )

    assert result[0]["password"] == "[REDACTED]"
    assert result[1][0]["token"] == "[REDACTED]"
    assert result[1][1] == "safe"


def test_redact_replaces_unsupported_objects():
    class InternalObject:
        pass

    assert redact(InternalObject()) == "<InternalObject>"


def test_trace_writer_creates_parent_directory_and_jsonl(tmp_path):
    trace_path = tmp_path / "nested" / "traces.jsonl"
    writer = JsonlTraceWriter(trace_path)

    writer.write({"event": "tool_completed", "status": "ok"})
    writer.write({"event": "tool_denied", "principal_id": "user-1"})

    lines = trace_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "tool_completed"
    assert json.loads(lines[1])["principal_id"] == "[REDACTED]"


def test_trace_writer_redacts_secrets_before_persisting(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    writer = JsonlTraceWriter(trace_path)

    writer.write(
        {
            "event": "request",
            "query": "private phrase",
            "authorization": "Bearer secret-value",
            "nested": {"password": "secret-password"},
        }
    )

    saved = trace_path.read_text(encoding="utf-8")

    assert "private phrase" not in saved
    assert "secret-value" not in saved
    assert "secret-password" not in saved
    assert "[REDACTED]" in saved


def test_trace_writer_rejects_non_dictionary_event(tmp_path):
    writer = JsonlTraceWriter(tmp_path / "trace.jsonl")

    with pytest.raises(TypeError):
        writer.write("not a dictionary")


def test_metrics_record_statuses_and_attempts():
    metrics = ReliabilityMetrics()

    metrics.record("ok", attempts=1)
    metrics.record("timeout", attempts=2)
    metrics.record("ok", attempts=1)

    snapshot = metrics.snapshot()

    assert snapshot["requests.total"] == 3
    assert snapshot["status.ok"] == 2
    assert snapshot["status.timeout"] == 1
    assert snapshot["provider.attempts"] == 4


def test_metrics_reject_invalid_values():
    metrics = ReliabilityMetrics()

    with pytest.raises(ValueError):
        metrics.record("", attempts=1)

    with pytest.raises(ValueError):
        metrics.record("ok", attempts=-1)

    with pytest.raises(ValueError):
        metrics.record("ok", attempts=True)


def test_metrics_snapshot_is_a_copy():
    metrics = ReliabilityMetrics()
    metrics.record("ok")

    snapshot = metrics.snapshot()
    snapshot["requests.total"] = 999

    assert metrics.snapshot()["requests.total"] == 1
