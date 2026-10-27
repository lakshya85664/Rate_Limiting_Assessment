
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str
    retry_after_seconds: float = 0.0
    scope: str = "none"


class SlidingWindowRateLimiter:
    """Thread-safe per-user/global limiter with replay protection."""

    def __init__(
        self,
        *,
        per_user_limit: int = 5,
        global_limit: int = 20,
        window_seconds: float = 60.0,
    ):
        if (
            not isinstance(per_user_limit, int)
            or isinstance(per_user_limit, bool)
            or per_user_limit < 1
        ):
            raise ValueError("per_user_limit must be a positive integer")

        if (
            not isinstance(global_limit, int)
            or isinstance(global_limit, bool)
            or global_limit < 1
        ):
            raise ValueError("global_limit must be a positive integer")

        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, (int, float))
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be positive")

        self.per_user_limit = per_user_limit
        self.global_limit = global_limit
        self.window_seconds = float(window_seconds)

        self._user_events: dict[str, list[float]] = {}
        self._global_events: list[float] = []

        # Keys are (authenticated principal ID, request ID).
        self._request_ids: dict[tuple[str, str], float] = {}

        self._lock = Lock()

    def _prune(self, now: float) -> None:
        """Remove expired quota events and replay records."""
        cutoff = now - self.window_seconds

        self._global_events = [
            timestamp
            for timestamp in self._global_events
            if timestamp > cutoff
        ]

        for principal_id in list(self._user_events):
            retained = [
                timestamp
                for timestamp in self._user_events[principal_id]
                if timestamp > cutoff
            ]

            if retained:
                self._user_events[principal_id] = retained
            else:
                del self._user_events[principal_id]

        expired_requests = [
            key
            for key, timestamp in self._request_ids.items()
            if timestamp <= cutoff
        ]

        for key in expired_requests:
            del self._request_ids[key]

    def claim_request(
        self,
        principal_id: str,
        request_id: str,
    ) -> bool:
        """
        Atomically claim a request ID for one principal.

        Returns False if that principal has already used this request ID
        within the active window. The caller must pass an authenticated
        principal ID, not an identity taken only from request arguments.
        """
        if (
            not isinstance(principal_id, str)
            or not principal_id.strip()
            or not isinstance(request_id, str)
            or not request_id.strip()
        ):
            return False

        now = monotonic()
        key = (principal_id, request_id)

        with self._lock:
            self._prune(now)

            if key in self._request_ids:
                return False

            self._request_ids[key] = now
            return True

    def check(self, principal_id: str) -> RateLimitDecision:
        """Atomically check and consume one quota slot."""
        if not isinstance(principal_id, str) or not principal_id.strip():
            return RateLimitDecision(
                allowed=False,
                reason="invalid_principal",
                scope="principal",
            )

        now = monotonic()

        with self._lock:
            self._prune(now)

            user_events = self._user_events.get(principal_id, [])

            if len(user_events) >= self.per_user_limit:
                retry_after = max(
                    0.0,
                    user_events[0] + self.window_seconds - now,
                )
                return RateLimitDecision(
                    allowed=False,
                    reason="per_user_limit_exceeded",
                    retry_after_seconds=retry_after,
                    scope="per_user",
                )

            if len(self._global_events) >= self.global_limit:
                retry_after = max(
                    0.0,
                    self._global_events[0] + self.window_seconds - now,
                )
                return RateLimitDecision(
                    allowed=False,
                    reason="global_limit_exceeded",
                    retry_after_seconds=retry_after,
                    scope="global",
                )

            self._user_events.setdefault(principal_id, []).append(now)
            self._global_events.append(now)

            return RateLimitDecision(
                allowed=True,
                reason="within_limits",
                scope="none",
            )
