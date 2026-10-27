
import pytest

from reliability.retry import execute_with_retries


def test_retry_succeeds_after_first_timeout():
    calls = {"count": 0}

    def flaky_operation(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary timeout")
        return {"ok": True}

    result = execute_with_retries(
        flaky_operation,
        kwargs={"query": "example"},
        max_attempts=3,
    )

    assert result.succeeded is True
    assert result.value == {"ok": True}
    assert result.attempts == 2
    assert calls["count"] == 2


def test_retry_stops_after_maximum_attempts():
    calls = {"count": 0}

    def always_times_out(**kwargs):
        calls["count"] += 1
        raise TimeoutError("provider unavailable")

    result = execute_with_retries(
        always_times_out,
        kwargs={},
        max_attempts=3,
    )

    assert result.succeeded is False
    assert result.timed_out is True
    assert result.attempts == 3
    assert calls["count"] == 3


def test_non_timeout_exception_is_not_retried():
    calls = {"count": 0}

    def fails_immediately(**kwargs):
        calls["count"] += 1
        raise RuntimeError("private internal detail")

    result = execute_with_retries(
        fails_immediately,
        kwargs={},
        max_attempts=5,
    )

    assert result.succeeded is False
    assert result.timed_out is False
    assert result.attempts == 1
    assert result.error_type == "RuntimeError"
    assert calls["count"] == 1


def test_successful_operation_runs_once():
    calls = {"count": 0}

    def successful_operation(**kwargs):
        calls["count"] += 1
        return ["result"]

    result = execute_with_retries(
        successful_operation,
        kwargs={},
        max_attempts=4,
    )

    assert result.succeeded is True
    assert result.value == ["result"]
    assert result.attempts == 1
    assert calls["count"] == 1


@pytest.mark.parametrize(
    "max_attempts",
    [0, -1, 6, True, 1.5],
)
def test_invalid_max_attempts_are_rejected(max_attempts):
    with pytest.raises(ValueError):
        execute_with_retries(
            lambda **kwargs: "ok",
            kwargs={},
            max_attempts=max_attempts,
        )


@pytest.mark.parametrize(
    "delay_seconds",
    [-1, 6, True, "invalid"],
)
def test_invalid_retry_delay_is_rejected(delay_seconds):
    with pytest.raises(ValueError):
        execute_with_retries(
            lambda **kwargs: "ok",
            kwargs={},
            delay_seconds=delay_seconds,
        )


def test_non_callable_operation_is_rejected():
    with pytest.raises(TypeError):
        execute_with_retries(
            None,
            kwargs={},
        )
