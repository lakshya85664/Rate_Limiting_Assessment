

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from authorization.gateway import dispatch
from reliability.observability import JsonlTraceWriter, ReliabilityMetrics
from reliability.rate_limiter import SlidingWindowRateLimiter

OUTPUT_DIR = ROOT / "outputs"
TRACE_DIR = ROOT / "traces"



def make_call(principal_id: str, request_id: str, query: str) -> dict[str, Any]:
    return {
        "name": "search",
        "arguments": {
            "request_id": request_id,
            "principal_id": principal_id,
            "query": query,
            "limit": 5,
            "action": "search",
        },
    }


def make_principal(principal_id: str) -> dict[str, str]:
    return {
        "principal_id": principal_id,
        "role": "support_writer",
    }


def success_provider(**kwargs: Any) -> list[dict[str, str]]:
    return [
        {
            "title": "Rate limiting guide",
            "snippet": "Example indexed search result.",
        }
    ]


def timeout_provider(**kwargs: Any) -> list[dict[str, str]]:
    raise TimeoutError("Internal provider timeout detail")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    trace_path = TRACE_DIR / "assessment_trace.jsonl"
    summary_path = OUTPUT_DIR / "evidence_summary.json"

    # Start this evidence run with a fresh trace file.
    trace_path.write_text("", encoding="utf-8")

    trace_writer = JsonlTraceWriter(trace_path)
    metrics = ReliabilityMetrics()
    scenarios: list[dict[str, Any]] = []

    def record_scenario(
        scenario_name: str,
        result: Any,
        *,
        attempts: int = 1,
    ) -> None:
        metrics.record(result.status, attempts=attempts)

        for event in result.events:
            trace_writer.write(
                {
                    "scenario": scenario_name,
                    "status": result.status,
                    "event": event,
                    "retry_after_seconds": result.retry_after_seconds,
                }
            )

        scenarios.append(
            {
                "scenario": scenario_name,
                "status": result.status,
                "expected_status": {
                    "successful_search": "ok",
                    "per_user_rate_limit": "rate_limited",
                    "duplicate_request": "denied",
                    "provider_timeout": "timeout",
                }[scenario_name],
                "passed": result.status
                == {
                    "successful_search": "ok",
                    "per_user_rate_limit": "rate_limited",
                    "duplicate_request": "denied",
                    "provider_timeout": "timeout",
                }[scenario_name],
                "attempts": attempts,
                "retry_after_seconds": result.retry_after_seconds,
            }
        )

    # Scenario 1: successful search.
    success_result = dispatch(
        make_call("evidence-user-1", "EVIDENCE-001", "example query"),
        make_principal("evidence-user-1"),
        handlers={"search": success_provider},
        rate_limiter=SlidingWindowRateLimiter(),
    )
    record_scenario("successful_search", success_result)

    # Scenario 2: second request exceeds the per-user limit.
    limited_limiter = SlidingWindowRateLimiter(
        per_user_limit=1,
        global_limit=10,
        window_seconds=60,
    )
    dispatch(
        make_call("evidence-user-2", "EVIDENCE-002A", "first query"),
        make_principal("evidence-user-2"),
        handlers={"search": success_provider},
        rate_limiter=limited_limiter,
    )
    limited_result = dispatch(
        make_call("evidence-user-2", "EVIDENCE-002B", "second query"),
        make_principal("evidence-user-2"),
        handlers={"search": success_provider},
        rate_limiter=limited_limiter,
    )
    record_scenario("per_user_rate_limit", limited_result)

    # Scenario 3: duplicate request ID is rejected.
    replay_limiter = SlidingWindowRateLimiter()
    replay_call = make_call(
        "evidence-user-3",
        "EVIDENCE-003",
        "replay demonstration",
    )
    replay_principal = make_principal("evidence-user-3")

    dispatch(
        replay_call,
        replay_principal,
        handlers={"search": success_provider},
        rate_limiter=replay_limiter,
    )
    replay_result = dispatch(
        replay_call,
        replay_principal,
        handlers={"search": success_provider},
        rate_limiter=replay_limiter,
    )
    record_scenario("duplicate_request", replay_result)

    # Scenario 4: provider times out on both bounded attempts.
    timeout_result = dispatch(
        make_call("evidence-user-4", "EVIDENCE-004", "timeout scenario"),
        make_principal("evidence-user-4"),
        handlers={"search": timeout_provider},
        rate_limiter=SlidingWindowRateLimiter(),
        retry_attempts=2,
    )
    timeout_attempts = next(
        (
            event["attempts"]
            for event in timeout_result.events
            if event.get("event") == "provider_execution"
        ),
        1,
    )
    record_scenario(
        "provider_timeout",
        timeout_result,
        attempts=timeout_attempts,
    )

    summary = {
        "project": "Rate Limiting Assessment",
        "evidence_version": "1.0",
        "scenario_count": len(scenarios),
        "passed_scenarios": sum(item["passed"] for item in scenarios),
        "all_scenarios_passed": all(item["passed"] for item in scenarios),
        "scenarios": scenarios,
        "metrics": metrics.snapshot(),
        "trace_file": "traces/assessment_trace.jsonl",
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("Topic 18 — Evidence Generation")
    print("=" * 40)
    print(f"Scenarios passed: {summary['passed_scenarios']}/{summary['scenario_count']}")
    print(f"Trace file: {trace_path}")
    print(f"Summary file: {summary_path}")
    print(f"All scenarios passed: {summary['all_scenarios_passed']}")


if __name__ == "__main__":
    main()
