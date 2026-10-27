
import pytest

from authorization.gateway import dispatch
from reliability.rate_limiter import SlidingWindowRateLimiter


def make_call(principal_id="user-1", request_id="REQ-001"):
    return {
        "name": "search",
        "arguments": {
            "request_id": request_id,
            "principal_id": principal_id,
            "query": "tool calling",
            "limit": 5,
            "action": "search",
        },
    }


def make_principal(principal_id="user-1", role="support_writer"):
    return {
        "principal_id": principal_id,
        "role": role,
    }


def fake_search(**kwargs):
    return [
        {
            "title": "Result",
            "snippet": "Example result",
        }
    ]


def run_dispatch(
    call=None,
    principal=None,
    handlers=None,
    rate_limiter=None,
):
    """Provide common defaults for gateway tests."""
    return dispatch(
        make_call() if call is None else call,
        make_principal() if principal is None else principal,
        handlers={"search": fake_search} if handlers is None else handlers,
        rate_limiter=(
            SlidingWindowRateLimiter()
            if rate_limiter is None
            else rate_limiter
        ),
    )


def test_gateway_executes_allowed_search():
    result = run_dispatch()

    assert result.status == "ok"
    assert result.data["results"][0]["title"] == "Result"
    assert result.error is None
    assert any(
        event["event"] == "tool_completed"
        for event in result.events
    )


def test_gateway_returns_rate_limited_status_and_retry_metadata():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=1,
        global_limit=10,
        window_seconds=60,
    )

    first = run_dispatch(
        call=make_call(request_id="REQ-001"),
        rate_limiter=limiter,
    )
    second = run_dispatch(
        call=make_call(request_id="REQ-002"),
        rate_limiter=limiter,
    )

    assert first.status == "ok"
    assert second.status == "rate_limited"
    assert second.retry_after_seconds is not None
    assert second.retry_after_seconds > 0
    assert second.error is not None


def test_gateway_rejects_principal_mismatch():
    result = run_dispatch(
        call=make_call(principal_id="forged-user"),
        principal=make_principal("user-1"),
    )

    assert result.status == "denied"
    assert result.events[0]["reason"] == "principal_mismatch"


def test_gateway_does_not_call_provider_when_rate_limited():
    calls = {"count": 0}

    def tracked_search(**kwargs):
        calls["count"] += 1
        return fake_search(**kwargs)

    limiter = SlidingWindowRateLimiter(
        per_user_limit=1,
        global_limit=10,
    )

    run_dispatch(
        call=make_call(request_id="REQ-001"),
        handlers={"search": tracked_search},
        rate_limiter=limiter,
    )

    second = run_dispatch(
        call=make_call(request_id="REQ-002"),
        handlers={"search": tracked_search},
        rate_limiter=limiter,
    )

    assert second.status == "rate_limited"
    assert calls["count"] == 1


def test_gateway_rejects_non_object_request():
    result = run_dispatch(call=["search"])

    assert result.status == "invalid"
    assert result.error == "Invalid tool request."


def test_gateway_rejects_unknown_tool():
    call = make_call()
    call["name"] = "unknown_tool"

    result = run_dispatch(call=call)

    assert result.status == "denied"
    assert result.events[0]["reason"] == "unknown_tool"


def test_gateway_rejects_non_object_principal():
    result = run_dispatch(principal=None)

    # The helper's None means "use its default", so call dispatch directly.
    result = dispatch(
        make_call(),
        None,
        handlers={"search": fake_search},
        rate_limiter=SlidingWindowRateLimiter(),
    )

    assert result.status == "denied"
    assert result.events[0]["reason"] == "invalid_principal"


def test_gateway_rejects_unauthorized_role():
    result = run_dispatch(
        principal=make_principal(role="guest"),
    )

    assert result.status == "denied"
    assert result.events[0]["reason"] == "role_or_principal_not_allowed"


def test_gateway_rejects_non_object_arguments():
    call = make_call()
    call["arguments"] = "not-an-object"

    result = run_dispatch(call=call)

    assert result.status == "invalid"
    assert result.events[0]["reason"] == "arguments_not_object"


def test_gateway_rejects_invalid_schema_arguments():
    call = make_call()
    call["arguments"]["limit"] = "five"

    result = run_dispatch(call=call)

    assert result.status == "invalid"
    assert result.events[0]["reason"] == "schema_validation_failed"


def test_gateway_returns_safe_timeout_result():
    def timeout_search(**kwargs):
        raise TimeoutError("internal server address and credentials")

    result = run_dispatch(handlers={"search": timeout_search})

    assert result.status == "timeout"
    assert result.error == "The search provider timed out."
    assert "credentials" not in result.error
    assert result.events[-1]["event"] == "provider_timeout"


def test_gateway_returns_safe_invalid_provider_response():
    def invalid_search(**kwargs):
        return [{"unexpected_field": "invalid result"}]

    result = run_dispatch(handlers={"search": invalid_search})

    assert result.status == "failed"
    assert result.error == "The search provider returned an invalid response."
    assert result.events[-1]["event"] == "provider_invalid_response"


def test_gateway_hides_unexpected_provider_exception_details():
    secret_message = "private internal endpoint and secret token"

    def failing_search(**kwargs):
        raise RuntimeError(secret_message)

    result = run_dispatch(handlers={"search": failing_search})

    assert result.status == "failed"
    assert result.error == "The search provider encountered an internal error."
    assert secret_message not in str(result)
    assert result.events[-1]["event"] == "provider_error"


def test_gateway_handles_missing_provider_handler():
    result = run_dispatch(handlers={})

    assert result.status == "failed"
    assert result.error == "The search provider is currently unavailable."
    assert result.events[0]["reason"] == "handler_unavailable"


def test_gateway_does_not_call_provider_for_unauthorized_role():
    calls = {"count": 0}

    def tracked_search(**kwargs):
        calls["count"] += 1
        return fake_search(**kwargs)

    result = run_dispatch(
        principal=make_principal(role="guest"),
        handlers={"search": tracked_search},
    )

    assert result.status == "denied"
    assert calls["count"] == 0


def test_gateway_does_not_call_provider_for_invalid_arguments():
    calls = {"count": 0}

    def tracked_search(**kwargs):
        calls["count"] += 1
        return fake_search(**kwargs)

    call = make_call()
    call["arguments"]["query"] = "   "

    result = run_dispatch(
        call=call,
        handlers={"search": tracked_search},
    )

    assert result.status == "invalid"
    assert calls["count"] == 0
