
# Topic 18: Implement Rate Limiting in Code

## 1. Project Overview

This project implements a protected search tool with per-user and global rate limiting. It demonstrates how to validate tool requests, authorize users, enforce quotas, prevent duplicate requests, handle provider failures, and capture redacted execution traces.

The implementation uses Python, Pydantic, and pytest. The rate limiter uses a thread-safe sliding-window approach, while the gateway applies validation and authorization checks before executing the provider.

## 2. Objectives

- Define typed input and output contracts for a search tool.
- Maintain a registry of explicitly registered tools.
- Validate requests and reject malformed arguments.
- Enforce independent per-user and global request quotas.
- Return rate-limit decisions with retry-after metadata.
- Reject unauthorized principals and mismatched identities.
- Prevent duplicate request IDs within the replay-protection window.
- Retry provider timeouts with a bounded number of attempts.
- Return safe errors without exposing internal exception messages.
- Generate structured, redacted JSONL traces and evidence summaries.
- Validate behavior with automated tests.

## 3. Project Structure

```text
Rate_Limiting_Assessment/
├── adapters/
├── authorization/
│   └── gateway.py
├── outputs/
│   ├── evidence_summary.json
│   └── generate_evidence.py
├── reliability/
│   ├── observability.py
│   ├── rate_limiter.py
│   └── retry.py
├── reports/
│   └── operator_report.md
├── schemas/
│   ├── registry.py
│   └── tool_contract.py
├── tests/
│   ├── test_task1.py
│   ├── test_task2.py
│   ├── test_task2_gateway.py
│   ├── test_task4_observability.py
│   ├── test_task4_reliability.py
│   └── test_task4_retry.py
├── traces/
│   └── assessment_trace.jsonl
├── requirements.txt
├── README.md
└── .gitignore
```

## 4. Technologies

- Python
- Pydantic for schema validation
- pytest for automated testing
- Python threading primitives for synchronization
- JSON and JSONL for evidence and event traces

## 5. Architecture and Request Flow

The request passes through these stages:

1. Validate the request structure.
2. Resolve the tool from the registry.
3. Verify the authenticated principal and permitted role.
4. Validate search arguments and bind the request to the authenticated identity.
5. Reject previously used request IDs.
6. Apply the per-user and global rate limits.
7. Execute the search provider with bounded timeout retries.
8. Validate the provider response.
9. Return the result or a safe failure response.
10. Record structured events and generate evidence.

The sliding-window rate limiter protects shared quota state with a lock. Replay protection uses the authenticated principal and request ID as its key.

## 6. Implementation Tasks

### Task 1: Tool Contract and Registry

Defined typed search input, search result, output, and tool metadata models. The schemas reject unexpected fields and invalid values. The registry exposes the explicitly registered search tool.

### Task 2: Rate Limiting

Implemented per-user and global sliding-window quotas. Rejected requests receive a status and retry-after metadata. The gateway prevents rejected requests from reaching the provider.

### Task 3: Validation, Security, and Failure Handling

Added checks for malformed requests, unknown tools, unauthorized roles, identity mismatches, invalid arguments, provider failures, and timeouts. Public errors use safe messages rather than raw provider exception details.

### Task 4: Reliability and Observability

Added in-memory replay protection, thread-safe quota checks, bounded timeout retries, recursive trace redaction, JSONL trace writing, and reliability counters. Evidence generation exercises successful search, quota rejection, duplicate request rejection, and provider timeout behavior.

## 7. Setup Instructions

Open Windows Command Prompt and navigate to the project directory:

```bat
cd /d E:\Tayana_Projects\Tool_Calling_Engineering\Rate_Limiting_Assessment
```

Create a virtual environment if one does not already exist:

```bat
python -m venv .venv
```

Activate it:

```bat
.venv\Scripts\activate
```

Install dependencies:

```bat
python -m pip install -r requirements.txt
```

## 8. Run the Tests

Run the complete test suite:

```bat
python -m pytest -q
```

### Verified test result

The recorded full-suite result was:

```text
68 passed in 0.16s
```

This result reflects the project state at the time of that test run. Run the tests again after any further changes.

## 9. Generate Evidence

Run the evidence generator:

```bat
python outputs\generate_evidence.py
```

The script creates or updates:

- `outputs/evidence_summary.json`
- `traces/assessment_trace.jsonl`

### Verified evidence result

```text
Scenarios passed: 4/4
All scenarios passed: True
```

The four scenarios are:

| Scenario | Expected status |
|---|---|
| Successful search | `ok` |
| Per-user rate limit | `rate_limited` |
| Duplicate request | `denied` |
| Provider timeout | `timeout` |

The recorded evidence summary reports five provider attempts across four scenarios. The timeout scenario makes two bounded attempts.

## 10. Security Considerations

- Input schemas reject unexpected fields and invalid types.
- The gateway checks the authenticated identity against the request identity.
- Unknown tools and unauthorized roles are rejected.
- Rate-limit decisions are made atomically.
- Duplicate request IDs are rejected within the configured in-memory window.
- Provider errors are mapped to safe public messages.
- Trace redaction removes configured sensitive fields before writing events.

## 11. Known Limitations

- Rate-limit and replay-protection state is held in memory. It does not persist through process restarts or coordinate across multiple application instances.
- Retry behavior currently targets provider timeouts and is bounded by the configured attempt count.
- The evidence scenarios are functional checks, not production-scale load tests.
- The demonstration uses a search provider handler rather than a production search service.
- The implementation does not provide a distributed rate limiter or durable replay store.

## 12. Reflection

This project helped me understand that implementing rate limiting requires more than counting requests. A reliable tool gateway must validate input, authenticate and authorize the caller, enforce quota boundaries, and provide clear outcomes when a request cannot proceed.

The sliding-window rate limiter demonstrated how per-user and global limits can be enforced independently. Using a lock around quota updates made the decision process atomic under concurrent requests. Retry-after metadata also gave rejected callers useful information about when they could try again.

The gateway implementation highlighted the importance of validating requests before calling an external provider. Checking the authenticated principal against the supplied identity prevents callers from selecting another user's quota. Replay protection added another layer by rejecting repeated request IDs within the active window.

Failure handling was another important lesson. Provider timeouts should not cause unlimited retries, and unexpected exceptions should not be returned directly to the caller. Bounded retry logic and generic public error messages help keep failures controlled and reduce the exposure of internal details.

The observability work demonstrated how structured JSONL traces and simple counters can make system behavior easier to inspect. Redacting sensitive fields before writing traces is important because logs can otherwise retain information that should not be exposed.

The evidence generator made it possible to reproduce success, rate-limit rejection, replay rejection, and timeout scenarios. Automated tests helped verify these behaviors consistently.

A key limitation is that the current quota and replay state is stored in memory. A production deployment would need shared state for multiple instances, durable replay protection, operational monitoring, and load testing. Overall, this project strengthened my understanding of secure tool execution, concurrency, failure recovery, and test-driven development.



