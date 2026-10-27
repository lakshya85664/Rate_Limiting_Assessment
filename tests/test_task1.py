
import pytest
from pydantic import ValidationError

from schemas.registry import build_registry, get_tool
from schemas.tool_contract import (
    SearchInput,
    SearchOutput,
    ToolContract,
)


def valid_search_input() -> dict:
    return {
        "request_id": "req-001",
        "principal_id": "user-001",
        "query": "rate limiting",
        "limit": 5,
        "action": "search",
    }


def test_search_input_accepts_valid_payload():
    model = SearchInput.model_validate(valid_search_input())

    assert model.request_id == "req-001"
    assert model.principal_id == "user-001"
    assert model.query == "rate limiting"
    assert model.limit == 5


def test_search_input_rejects_missing_principal():
    payload = valid_search_input()
    del payload["principal_id"]

    with pytest.raises(ValidationError):
        SearchInput.model_validate(payload)


def test_search_input_rejects_string_limit():
    payload = valid_search_input()
    payload["limit"] = "5"

    with pytest.raises(ValidationError):
        SearchInput.model_validate(payload)


def test_search_input_rejects_limit_below_range():
    payload = valid_search_input()
    payload["limit"] = 0

    with pytest.raises(ValidationError):
        SearchInput.model_validate(payload)


def test_search_input_rejects_limit_above_range():
    payload = valid_search_input()
    payload["limit"] = 21

    with pytest.raises(ValidationError):
        SearchInput.model_validate(payload)


def test_search_input_rejects_unknown_fields():
    payload = valid_search_input()
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        SearchInput.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_id", "   "),
        ("principal_id", "   "),
        ("query", "   "),
    ],
)
def test_search_input_rejects_blank_strings(field, value):
    payload = valid_search_input()
    payload[field] = value

    with pytest.raises(ValidationError):
        SearchInput.model_validate(payload)


def test_registry_contains_search_tool():
    registry = build_registry()

    assert "search" in registry
    assert registry["search"].name == "search"
    assert registry["search"].access == "read"
    assert registry["search"].requires_authentication is True


def test_registry_returns_none_for_unknown_tool():
    assert get_tool("unknown_tool") is None


def test_registry_returns_fresh_instances():
    first = build_registry()
    second = build_registry()

    assert first is not second
    assert first["search"] is not second["search"]


def test_search_output_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SearchOutput.model_validate(
            {
                "request_id": "req-001",
                "status": "ok",
                "results": [],
                "unexpected": True,
            }
        )


def test_tool_contract_rejects_empty_allowed_roles():
    with pytest.raises(ValidationError):
        ToolContract(
            name="test",
            version="1.0",
            description="Test tool",
            access="read",
            allowed_roles=[],
            allowed_actions=["search"],
            input_schema="SearchInput",
            output_schema="SearchOutput",
        )
