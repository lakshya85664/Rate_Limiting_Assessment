
from dataclasses import dataclass
from time import sleep
from typing import Any, Callable


@dataclass(frozen=True)
class RetryResult:
    succeeded: bool
    value: Any = None
    attempts: int = 0
    timed_out: bool = False
    error_type: str | None = None


def execute_with_retries(
    operation: Callable[..., Any],
    *,
    kwargs: dict[str, Any],
    max_attempts: int = 2,
    delay_seconds: float = 0.0,
) -> RetryResult:
    """Execute an operation with bounded retries for timeouts only."""
    if not callable(operation):
        raise TypeError("operation must be callable")

    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts < 1
        or max_attempts > 5
    ):
        raise ValueError("max_attempts must be an integer from 1 to 5")

    if (
        isinstance(delay_seconds, bool)
        or not isinstance(delay_seconds, (int, float))
        or delay_seconds < 0
        or delay_seconds > 5
    ):
        raise ValueError("delay_seconds must be between 0 and 5")

    for attempt in range(1, max_attempts + 1):
        try:
            value = operation(**kwargs)
            return RetryResult(
                succeeded=True,
                value=value,
                attempts=attempt,
            )
        except TimeoutError:
            if attempt < max_attempts and delay_seconds > 0:
                sleep(delay_seconds * attempt)

            if attempt == max_attempts:
                return RetryResult(
                    succeeded=False,
                    attempts=attempt,
                    timed_out=True,
                    error_type="TimeoutError",
                )
        except Exception as exc:
            # Do not expose the exception message; the gateway maps
            # the exception type to a safe public error.
            return RetryResult(
                succeeded=False,
                attempts=attempt,
                timed_out=False,
                error_type=type(exc).__name__,
            )

    # Defensive fallback; normal control flow returns inside the loop.
    return RetryResult(
        succeeded=False,
        attempts=max_attempts,
        error_type="UnknownError",
    )
