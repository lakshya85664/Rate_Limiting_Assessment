
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)


class SearchInput(BaseModel):
    """Validated input contract for the protected search tool."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: StrictStr = Field(min_length=1, max_length=64)
    principal_id: StrictStr = Field(min_length=1, max_length=64)
    query: StrictStr = Field(min_length=1, max_length=500)
    limit: StrictInt = Field(default=5, ge=1, le=20)
    action: Literal["search"] = "search"

    @field_validator("request_id", "principal_id", "query")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        """Reject strings that contain only whitespace."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class SearchResultItem(BaseModel):
    """One result returned by the search provider."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: StrictStr = Field(min_length=1, max_length=200)
    snippet: StrictStr = Field(max_length=1000)

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class SearchOutput(BaseModel):
    """Typed output contract for search execution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: StrictStr
    status: Literal[
        "ok",
        "invalid",
        "denied",
        "rate_limited",
        "timeout",
        "failed",
    ]
    results: list[SearchResultItem] = Field(default_factory=list)
    error: StrictStr | None = None
    retry_after_seconds: float | None = Field(default=None, ge=0)


class ToolContract(BaseModel):
    """Metadata and policy for a registered tool."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: StrictStr = Field(min_length=1, max_length=64)
    version: StrictStr = Field(min_length=1, max_length=16)
    description: StrictStr = Field(min_length=1, max_length=256)
    access: Literal["read", "write"]
    allowed_roles: list[StrictStr] = Field(min_length=1)
    allowed_actions: list[StrictStr] = Field(min_length=1)
    input_schema: StrictStr
    output_schema: StrictStr
    requires_authentication: bool = True


def build_tool_contracts() -> dict[str, ToolContract]:
    """Build the explicitly registered tool contracts."""
    search = ToolContract(
        name="search",
        version="1.0.0",
        description=(
            "Search indexed documents under per-user and global rate limits."
        ),
        access="read",
        allowed_roles=["support_writer", "billing_operator", "admin"],
        allowed_actions=["search"],
        input_schema=SearchInput.__name__,
        output_schema=SearchOutput.__name__,
        requires_authentication=True,
    )

    return {search.name: search}
