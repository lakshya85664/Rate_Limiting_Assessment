
from reliability.rate_limiter import SlidingWindowRateLimiter


def test_requests_within_per_user_and_global_limits_are_allowed():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=2,
        global_limit=5,
        window_seconds=60,
    )

    assert limiter.check("user-1").allowed is True
    assert limiter.check("user-1").allowed is True


def test_per_user_limit_returns_retry_metadata():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=1,
        global_limit=5,
        window_seconds=60,
    )

    assert limiter.check("user-1").allowed is True
    decision = limiter.check("user-1")

    assert decision.allowed is False
    assert decision.reason == "per_user_limit_exceeded"
    assert decision.scope == "per_user"
    assert 0 < decision.retry_after_seconds <= 60


def test_global_limit_applies_across_users():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=5,
        global_limit=2,
        window_seconds=60,
    )

    assert limiter.check("user-1").allowed is True
    assert limiter.check("user-2").allowed is True

    decision = limiter.check("user-3")

    assert decision.allowed is False
    assert decision.reason == "global_limit_exceeded"
    assert decision.scope == "global"
    assert 0 < decision.retry_after_seconds <= 60


def test_user_quota_is_independent_between_users():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=1,
        global_limit=5,
        window_seconds=60,
    )

    assert limiter.check("user-1").allowed is True
    assert limiter.check("user-1").allowed is False
    assert limiter.check("user-2").allowed is True


def test_denied_request_does_not_consume_global_quota():
    limiter = SlidingWindowRateLimiter(
        per_user_limit=1,
        global_limit=2,
        window_seconds=60,
    )

    assert limiter.check("user-1").allowed is True
    assert limiter.check("user-1").allowed is False
    assert limiter.check("user-2").allowed is True


def test_empty_principal_is_rejected():
    limiter = SlidingWindowRateLimiter()

    decision = limiter.check(" ")

    assert decision.allowed is False
    assert decision.reason == "invalid_principal"


def test_invalid_limits_are_rejected():
    for kwargs in (
        {"per_user_limit": 0},
        {"global_limit": 0},
        {"window_seconds": 0},
    ):
        try:
            SlidingWindowRateLimiter(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {kwargs}")
