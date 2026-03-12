from typing import Any
import importlib
from imports.mcp.base import MCPServer

class BaseToolsMCP(MCPServer):
    """MCP server that manages the base agent tools."""
    
    def __init__(self) -> None:
        self._tool_table: dict[str, Any] = self._load_tools()

    @staticmethod
    def _load_tools() -> dict[str, Any]:
        """Dynamically import tool modules and build name -> callable map."""
        tool_table: dict[str, Any] = {}
        tool_names = ["current_weather", "web_search", "web_fetch", "file_io", "file_list"]
        for tool_name in tool_names:
            try:
                module = importlib.import_module(f"imports.tools.{tool_name}")
                tool_table[tool_name] = getattr(module, tool_name)
            except Exception as e:
                print(f"BaseToolsMCP failed to load tool {tool_name}: {e}")
        return tool_table

    def _rpc_tool_execute(self, params: dict) -> Any:
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
