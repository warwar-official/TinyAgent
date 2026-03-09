from typing import Any
import importlib
from imports.mcp.base import MCPServer


class BaseToolsMCP(MCPServer):
    """MCP server that manages the base agent tools.

    Takes over tool loading, tool schema reporting, and tool execution
    from LoopManager.  The existing tool modules in ``imports/tools/``
    are loaded dynamically and called exactly as before.
    """

    def __init__(self, config: dict) -> None:
        self._tool_configs: list[dict] = config.get("tools", [])
        self._tool_table: dict[str, Any] = self._load_tools(self._tool_configs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_tools(tool_configs: list[dict]) -> dict[str, Any]:
        """Dynamically import tool modules and build name -> callable map."""
        tool_table: dict[str, Any] = {}
        for tool_cfg in tool_configs:
            tool_name = tool_cfg["name"]
            module = importlib.import_module(f"imports.tools.{tool_name}")
            tool_table[tool_name] = getattr(module, tool_name)
        return tool_table

    # ------------------------------------------------------------------
    # RPC handlers
    # ------------------------------------------------------------------

    def _rpc_tool_list(self, params: dict) -> list[dict]:
        """Return tool schemas for every registered tool."""
        schemas: list[dict] = []
        for tool_cfg in self._tool_configs:
            schemas.append({
                "name": tool_cfg["name"],
                "description": tool_cfg.get("description", ""),
                "parameters": tool_cfg.get("parameters", {}),
            })
        return schemas

    def _rpc_tool_execute(self, params: dict) -> Any:
        """Execute a tool by name with the given arguments.

        Expected *params*::

            {"name": "web_search", "arguments": {"query": "...", "count": 3}}

        Returns:
            The tool's result dict (unchanged format from the tool module).

        Raises:
            ValueError: If the tool name is unknown.
        """
        name: str = params["name"]
        arguments: dict = params.get("arguments", {})

        if name not in self._tool_table:
            return {
                "tool_name": name,
                "tool_arguments": arguments,
                "tool_result": None,
                "truncate": False,
                "error": "Error: Tool not found",
            }

        try:
            return self._tool_table[name](**arguments)
        except Exception as e:
            return {
                "tool_name": name,
                "tool_arguments": arguments,
                "tool_result": None,
                "truncate": False,
                "error": str(e),
            }
