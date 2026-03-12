from typing import Any
from imports.mcp.base import MCPServer


class MCPConnector:
    """Routing layer between LoopManager and MCP servers.

    Aggregates tools, prompts, and ability descriptions from all registered
    servers and routes calls to the correct server.
    """

    def __init__(self, servers: list[MCPServer]) -> None:
        self._servers: list[MCPServer] = servers
        self._tool_registry: dict[str, MCPServer] = {}    # tool_name -> server
        self._prompt_registry: dict[str, MCPServer] = {}   # prompt_name -> server
        self._tool_schemas: list[dict] = []
        self._prompt_schemas: list[dict] = []
        self._ability_prompts: list[str] = []
        self._discover()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:
        """Query every server for its tools, prompts, and ability prompt."""
        for server in self._servers:
            # Tools
            try:
                tools = server.handle_rpc("tool_list", {})
                if isinstance(tools, list):
                    for tool in tools:
                        name = tool.get("name", "")
                        if name:
                            self._tool_registry[name] = server
                            self._tool_schemas.append(tool)
            except ValueError:
                pass  # server doesn't support tool_list

            # Prompts
            try:
                prompts = server.handle_rpc("prompt_list", {})
                if isinstance(prompts, list):
                    for prompt in prompts:
                        name = prompt.get("name", "")
                        if name:
                            self._prompt_registry[name] = server
                            self._prompt_schemas.append(prompt)
            except ValueError:
                pass  # server doesn't support prompt_list

            # Ability prompt (optional resource)
            try:
                ability = server.handle_rpc("ability_prompt", {})
                if isinstance(ability, str) and ability.strip():
                    self._ability_prompts.append(ability)
            except ValueError:
                pass  # server doesn't provide ability_prompt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tools(self) -> list[dict]:
        """Return aggregated tool schemas from all servers."""
        return list(self._tool_schemas)

    def execute_tool(self, name: str, arguments: dict) -> Any:
        """Route a tool call to the owning MCP server."""
        server = self._tool_registry.get(name)
        if server is None:
            raise ValueError(f"Tool '{name}' is not registered in any MCP server.")
        return server.handle_rpc("tool_execute", {"name": name, "arguments": arguments})

    def get_prompts(self) -> list[dict]:
        """Return aggregated prompt schemas from all servers."""
        return list(self._prompt_schemas)

    def generate_prompt(self, name: str, arguments: dict) -> str:
        """Route a prompt generation request to the owning MCP server."""
        server = self._prompt_registry.get(name)
        if server is None:
            raise ValueError(f"Prompt '{name}' is not registered in any MCP server.")
        return server.handle_rpc("prompt_generate", {"name": name, "arguments": arguments})

    def get_ability_prompt(self) -> str:
        """Return concatenated ability prompts from all servers."""
        return "\n\n".join(self._ability_prompts)
