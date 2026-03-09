from typing import Any
from imports.mcp.base import MCPServer


class MCPConnector:
    """Routing layer between LoopManager and MCP servers.

    Aggregates tools and prompts from all registered servers and routes
    ``execute_tool`` / ``generate_prompt`` calls to the correct server.
    """

    def __init__(self, servers: list[MCPServer]) -> None:
        self._servers: list[MCPServer] = servers
        self._tool_registry: dict[str, MCPServer] = {}    # tool_name -> server
        self._prompt_registry: dict[str, MCPServer] = {}   # prompt_name -> server
        self._tool_schemas: list[dict] = []
        self._prompt_schemas: list[dict] = []
        self._discover()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:
        """Query every server for its tools and prompts."""
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tools(self) -> list[dict]:
        """Return aggregated tool schemas from all servers."""
        return list(self._tool_schemas)

    def execute_tool(self, name: str, arguments: dict) -> Any:
        """Route a tool call to the owning MCP server.

        Args:
            name:      Tool name (e.g. ``"web_search"``).
            arguments: Keyword arguments for the tool.

        Returns:
            Whatever the tool function returns (typically a dict).

        Raises:
            ValueError: If no server owns a tool with the given *name*.
        """
        server = self._tool_registry.get(name)
        if server is None:
            raise ValueError(f"Tool '{name}' is not registered in any MCP server.")
        return server.handle_rpc("tool_execute", {"name": name, "arguments": arguments})

    def get_prompts(self) -> list[dict]:
        """Return aggregated prompt schemas from all servers."""
        return list(self._prompt_schemas)

    def generate_prompt(self, name: str, arguments: dict) -> str:
        """Route a prompt generation request to the owning MCP server.

        Args:
            name:      Prompt name (e.g. ``"system_prompt"``).
            arguments: Data required by the prompt builder.

        Returns:
            The rendered prompt string.

        Raises:
            ValueError: If no server owns a prompt with the given *name*.
        """
        server = self._prompt_registry.get(name)
        if server is None:
            raise ValueError(f"Prompt '{name}' is not registered in any MCP server.")
        return server.handle_rpc("prompt_generate", {"name": name, "arguments": arguments})
