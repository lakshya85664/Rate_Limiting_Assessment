
from concurrent.futures import ThreadPoolExecutor

from authorization.gateway import dispatch
from reliability.rate_limiter import SlidingWindowRateLimiter


def make_call(principal_id="user-1", request_id="REQ-001"):
    return {
        "name": "search",
        "arguments": {
            "request_id": request_id,
            "principal_id": principal_id,
            "query": "reliability testing",
            "limit": 5,
            "action": "search",
        },
    }


def make_principal(principal_id="user-1"):
    return {
        "principal_id": principal_id,
        "role": "support_writer",
    }


def test_concurrent_requests_never_exceed_user_or_global_limit():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=10,
        global_limit=10,
        window_seconds=60,
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(
            executor.map(
                limiter.check,
                ["same-user"] * 100,
            )
        )

    allowed_count = sum(decision.allowed for decision in decisions)

    assert allowed_count == 10
    assert all(
        decision.reason in {
            "within_limits",
            "per_user_limit_exceeded",
            "global_limit_exceeded",
        }
        for decision in decisions
    )


def test_concurrent_users_cannot_exceed_global_limit():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=10,
        global_limit=7,
        window_seconds=60,
    )

    principals = [f"user-{index}" for index in range(50)]

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(executor.map(limiter.check, principals))

    assert sum(decision.allowed for decision in decisions) == 7
    assert sum(
        decision.scope == "global"
        for decision in decisions
    ) == 43


def test_request_id_can_be_claimed_only_once_per_principal():
    limiter = SlidingWindowRateLimiter()

    assert limiter.claim_request("user-1", "REQ-001") is True
    assert limiter.claim_request("user-1", "REQ-001") is False


def test_same_request_id_is_allowed_for_different_principals():
    limiter = SlidingWindowRateLimiter()

    assert limiter.claim_request("user-1", "REQ-001") is True
    assert limiter.claim_request("user-2", "REQ-001") is True


def test_concurrent_duplicate_request_ids_are_claimed_once():
    limiter = SlidingWindowRateLimiter()

    def claim():
        return limiter.claim_request("user-1", "REQ-CONCURRENT")

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda _: claim(), range(50)))

    assert sum(results) == 1


def test_gateway_rejects_replayed_request_without_calling_provider():
    limiter = SlidingWindowRateLimiter()
    provider_calls = {"count": 0}

    def provider(**kwargs):
        provider_calls["count"] += 1
        return [{"title": "Result", "snippet": "Safe result"}]

    first = dispatch(
        make_call(),
        make_principal(),
        handlers={"search": provider},
        rate_limiter=limiter,
    )

    replay = dispatch(
        make_call(),
        make_principal(),
        handlers={"search": provider},
        rate_limiter=limiter,
    )

    assert first.status == "ok"
    assert replay.status == "denied"
    assert replay.events[0]["event"] == "replay_rejected"
    assert provider_calls["count"] == 1


def test_invalid_request_id_is_not_claimed():
    limiter = SlidingWindowRateLimiter()

    assert limiter.claim_request("", "REQ-001") is False
    assert limiter.claim_request("user-1", "") is False
    assert limiter.claim_request(" ", "REQ-001") is False
    assert limiter.claim_request("user-1", " ") is False


def test_boolean_limits_are_rejected():
    for kwargs in (
        {"per_user_limit": True},
        {"global_limit": False},
        {"window_seconds": True},
    ):
        try:
            SlidingWindowRateLimiter(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Expected ValueError for {kwargs}"
            )
