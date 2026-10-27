
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import ValidationError

from reliability.rate_limiter import SlidingWindowRateLimiter
from reliability.retry import execute_with_retries
from schemas.registry import build_registry
from schemas.tool_contract import SearchInput, SearchOutput


@dataclass
class ToolResult:
    """Consistent, safe result envelope for tool execution."""

    status: str
    data: dict[str, Any] = field(default_factory=dict)
    next_action: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    retry_after_seconds: float | None = None
    error: str | None = None


def dispatch(
    call: Any,
    principal: Any,
    *,
    handlers: dict[str, Callable[..., list[dict]]],
    rate_limiter: SlidingWindowRateLimiter,
    retry_attempts: int = 2,
) -> ToolResult:
    """Validate, authorize, deduplicate, rate-limit, and execute a tool."""
    if not isinstance(call, dict):
        return ToolResult(
            status="invalid",
            error="Invalid tool request.",
            next_action="provide_tool_request",
            events=[
                {"event": "input_rejected", "reason": "request_not_object"}
            ],
        )

    name = call.get("name")
    contract = (
        build_registry().get(name)
        if isinstance(name, str)
        else None
    )

    if contract is None:
        return ToolResult(
            status="denied",
            error="The requested tool is not available.",
            next_action="choose_registered_tool",
            events=[
                {"event": "tool_denied", "reason": "unknown_tool"}
            ],
        )

    if not isinstance(principal, dict):
        return ToolResult(
            status="denied",
            error="Authentication is required.",
            next_action="authenticate",
            events=[
                {"event": "authorization_denied", "reason": "invalid_principal"}
            ],
        )

    role = principal.get("role")
    principal_id = principal.get("principal_id")

    if (
        not isinstance(role, str)
        or role not in contract.allowed_roles
        or not isinstance(principal_id, str)
        or not principal_id.strip()
    ):
        return ToolResult(
            status="denied",
            error="The principal is not authorized to use this tool.",
            next_action="request_authorization",
            events=[
                {
                    "event": "authorization_denied",
                    "reason": "role_or_principal_not_allowed",
                }
            ],
        )

    if name != "search":
        return ToolResult(
            status="denied",
            error="The requested tool is not supported.",
            next_action="choose_registered_tool",
            events=[
                {"event": "tool_denied", "reason": "unsupported_tool"}
            ],
        )

    arguments = call.get("arguments")
    if not isinstance(arguments, dict):
        return ToolResult(
            status="invalid",
            error="Tool arguments must be an object.",
            next_action="correct_arguments",
            events=[
                {"event": "input_rejected", "reason": "arguments_not_object"}
            ],
        )

    try:
        validated = SearchInput.model_validate(arguments)
    except (ValidationError, TypeError, ValueError):
        return ToolResult(
            status="invalid",
            error="Tool arguments failed schema validation.",
            next_action="correct_arguments",
            events=[
                {
                    "event": "input_rejected",
                    "reason": "schema_validation_failed",
                }
            ],
        )

    if validated.principal_id != principal_id:
        return ToolResult(
            status="denied",
            error="The request principal does not match the authenticated user.",
            next_action="use_authenticated_principal",
            events=[
                {
                    "event": "authorization_denied",
                    "reason": "principal_mismatch",
                }
            ],
        )

    if validated.action not in contract.allowed_actions:
        return ToolResult(
            status="denied",
            error="The requested action is not authorized.",
            next_action="request_authorization",
            events=[
                {
                    "event": "authorization_denied",
                    "reason": "action_not_allowed",
                }
            ],
        )

    if (
        not isinstance(retry_attempts, int)
        or isinstance(retry_attempts, bool)
        or not 1 <= retry_attempts <= 5
    ):
        return ToolResult(
            status="invalid",
            error="Retry configuration must be between 1 and 5 attempts.",
            next_action="correct_retry_configuration",
            events=[
                {
                    "event": "configuration_rejected",
                    "reason": "invalid_retry_attempts",
                }
            ],
        )

    handler = handlers.get(name)
    if not callable(handler):
        return ToolResult(
            status="failed",
            error="The search provider is currently unavailable.",
            next_action="review_provider_configuration",
            events=[
                {
                    "event": "provider_error",
                    "reason": "handler_unavailable",
                }
            ],
        )

    if not rate_limiter.claim_request(
        principal_id,
        validated.request_id,
    ):
        return ToolResult(
            status="denied",
            error="This request ID has already been used.",
            next_action="create_new_request_id",
            events=[
                {
                    "event": "replay_rejected",
                    "reason": "duplicate_request_id",
                }
            ],
        )

    decision = rate_limiter.check(principal_id)
    events = [
        {
            "event": "rate_limit_decision",
            "allowed": decision.allowed,
            "scope": decision.scope,
            "reason": decision.reason,
        }
    ]

    if not decision.allowed:
        return ToolResult(
            status="rate_limited",
            error="Rate limit exceeded. Please retry after the indicated delay.",
            next_action="retry_after_window",
            retry_after_seconds=decision.retry_after_seconds,
            events=events,
        )

    retry_result = execute_with_retries(
        handler,
        kwargs={
            "query": validated.query,
            "limit": validated.limit,
        },
        max_attempts=retry_attempts,
    )

    events.append(
        {
            "event": "provider_execution",
            "attempts": retry_result.attempts,
            "succeeded": retry_result.succeeded,
        }
    )

    if not retry_result.succeeded:
        if retry_result.timed_out:
            return ToolResult(
                status="timeout",
                error="The search provider timed out.",
                next_action="retry_with_new_request_id_or_review",
                events=events + [{"event": "provider_timeout"}],
            )

        if retry_result.error_type in {
            "ValidationError",
            "TypeError",
            "ValueError",
        }:
            return ToolResult(
                status="failed",
                error="The search provider returned an invalid response.",
                next_action="review_provider_response",
                events=events + [
                    {"event": "provider_invalid_response"}
                ],
            )

        return ToolResult(
            status="failed",
            error="The search provider encountered an internal error.",
            next_action="review_provider_health",
            events=events + [{"event": "provider_error"}],
        )

    try:
        output = SearchOutput(
            request_id=validated.request_id,
            status="ok",
            results=retry_result.value,
        )
    except (ValidationError, TypeError, ValueError):
        return ToolResult(
            status="failed",
            error="The search provider returned an invalid response.",
            next_action="review_provider_response",
            events=events + [{"event": "provider_invalid_response"}],
        )

    events.append({"event": "tool_completed", "tool": name})

    return ToolResult(
        status=output.status,
        data=output.model_dump(),
        events=events,
    )
