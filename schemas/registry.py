
from schemas.tool_contract import ToolContract, build_tool_contracts


def build_registry() -> dict[str, ToolContract]:
    """Return a fresh registry of explicitly registered tools."""
    return build_tool_contracts()


def get_tool(
    name: str,
    registry: dict[str, ToolContract] | None = None,
) -> ToolContract | None:
    """Return a registered tool, or None if it is unknown."""
    active_registry = registry if registry is not None else build_registry()
    return active_registry.get(name)
