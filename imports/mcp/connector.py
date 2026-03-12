import json
import importlib
from typing import Any
from imports.mcp.base import MCPServer
from imports.mcp.remote import RemoteMCPServer


class MCPConnector:
    """Routing layer between LoopManager and MCP servers.

    Loads MCP servers dynamically from mcp_config.json.
    Aggregates tools, prompts, and ability descriptions from all registered
    servers and routes calls to the correct server.
    """

    def __init__(self, config_data: dict) -> None:
        self._servers: list[MCPServer] = []
        self._tool_registry: dict[str, MCPServer] = {}    # tool_name -> server
        self._prompt_registry: dict[str, MCPServer] = {}   # prompt_name -> server
        self._tool_schemas: list[dict] = []
        self._prompt_schemas: list[dict] = []
        self._ability_prompts: list[str] = []
        
        self._load_config(config_data)

    def _load_config(self, config_data: dict) -> None:
        """Read the config dictionary and instantiate the servers."""

        for server_cfg in config_data.get("servers", []):
            try:
                self._init_server(server_cfg)
            except Exception as e:
                print(f"Failed to initialize server {server_cfg.get('name')}: {e}")

    def _init_server(self, server_cfg: dict) -> None:
        """Instantiate single server from config and register its metadata."""
        stype = server_cfg.get("type")
        server_instance = None
        
        # 1. Instantiate based on type
        if stype == "local_class":
            module_name, class_name = server_cfg["class"].rsplit(".", 1)
            module = importlib.import_module(module_name)
            server_class = getattr(module, class_name)
            init_params = server_cfg.get("init_params", {})
            try:
                server_instance = server_class(**init_params)
            except TypeError as e:
                 print(f"Warning: {server_cfg['name']} init failed with kwargs, trying empty. ({e})")
                 server_instance = server_class()
        elif stype == "remote":
            url = server_cfg.get("url")
            if not url:
                raise ValueError("Remote server config must specify a 'url'.")
            server_instance = RemoteMCPServer(url)
        else:
            raise ValueError(f"Unknown server type: {stype}")

        if server_instance:
            self._servers.append(server_instance)

            # 2. Register Metadata from Config (Not from server RPC anymore)
            # Tools
            for tool in server_cfg.get("tools", []):
                name = tool.get("name")
                if name:
                    self._tool_registry[name] = server_instance
                    self._tool_schemas.append(tool)
            
            # Prompts
            for prompt in server_cfg.get("prompts", []):
                name = prompt.get("name")
                if name:
                    self._prompt_registry[name] = server_instance
                    self._prompt_schemas.append(prompt)
                    
            # Abilities
            for ability in server_cfg.get("abilities", []):
                if ability.strip():
                    self._ability_prompts.append(ability)

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
