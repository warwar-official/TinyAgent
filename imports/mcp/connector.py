import json
import importlib
import concurrent.futures
from typing import Any
from imports.mcp.base import MCPServer
from imports.mcp.remote import RemoteMCPServer


class MCPConnector:
    """Routing layer between LoopManager and MCP servers.

    Loads MCP servers dynamically from mcp_config.json.
    Aggregates tools, prompts, and ability descriptions from all registered
    servers and routes calls to the correct server.
    """

    def __init__(self, config_data: dict, app_config: dict | None = None, image_manager=None) -> None:
        self._servers: list[MCPServer] = []
        self._tool_registry: dict[str, MCPServer] = {}    # tool_name -> server
        self._tool_timeouts: dict[str, int] = {}            # tool_name -> timeout_seconds
        self._prompt_registry: dict[str, MCPServer] = {}   # prompt_name -> server
        self._tool_schemas: list[dict] = []
        self._prompt_schemas: list[dict] = []
        self._ability_prompts: list[str] = []
        self._server_abilities: dict[str, list[str]] = {}  # server_name -> abilities
        self._tool_to_server_name: dict[str, str] = {}     # tool_name -> server_name
        
        self.app_config = app_config
        self.image_manager = image_manager
        self.identity_mcp = None
        self.memory_mcp = None

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
        server_name = server_cfg.get("name", "unknown")
        server_instance = None
        
        # 1. Instantiate based on type
        if stype == "local_class":
            module_name, class_name = server_cfg["class"].rsplit(".", 1)
            module = importlib.import_module(module_name)
            server_class = getattr(module, class_name)
            init_params = server_cfg.get("init_params", {}).copy()
            
            if server_cfg.get("inject_app_config") and self.app_config:
                init_params["app_config"] = self.app_config
            
            if server_cfg.get("inject_image_manager") and self.image_manager:
                init_params["image_manager"] = self.image_manager

            try:
                server_instance = server_class(**init_params)
            except TypeError as e:
                 print(f"Warning: {server_name} init failed with kwargs, trying empty. ({e})")
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
            
            if server_name == "identity":
                self.identity_mcp = server_instance
            elif server_name == "memory":
                self.memory_mcp = server_instance

            # 2. Register Metadata from Config (Not from server RPC anymore)
            # Abilities (store per-server)
            server_abilities = [a for a in server_cfg.get("abilities", []) if a.strip()]
            self._server_abilities[server_name] = server_abilities
            
            # Tools
            for tool in server_cfg.get("tools", []):
                name = tool.get("name")
                if name:
                    self._tool_registry[name] = server_instance
                    self._tool_schemas.append(tool)
                    self._tool_to_server_name[name] = server_name
                    if "timeout" in tool:
                        self._tool_timeouts[name] = int(tool["timeout"])
            
            # Prompts
            for prompt in server_cfg.get("prompts", []):
                name = prompt.get("name")
                if name:
                    self._prompt_registry[name] = server_instance
                    self._prompt_schemas.append(prompt)
                    
            # Flat abilities list (backward compat)
            for ability in server_abilities:
                self._ability_prompts.append(ability)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_available_tools(self) -> list[dict]:
        """Return aggregated tool schemas from all servers."""
        return list(self._tool_schemas)

    def get_all_abilities(self) -> list[str]:
        """Return aggregated abilities from all servers.
        
        Returns a flat list of strings describing agent skills/capabilities.
        """
        return list(self._ability_prompts)

    def execute_tool(self, name: str, arguments: dict, timeout_seconds: int | None = None) -> Any:
        """Route a tool call to the owning MCP server with a timeout.
        
        Uses the per-tool timeout from config if set, otherwise falls back to
        timeout_seconds argument (default 30s).
        """
        server = self._tool_registry.get(name)
        if server is None:
            raise ValueError(f"Tool '{name}' is not registered in any MCP server.")
        
        # Per-tool timeout takes priority over the argument default
        effective_timeout = self._tool_timeouts.get(name, timeout_seconds if timeout_seconds is not None else 30)
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(server.handle_rpc, "tool_execute", {"name": name, "arguments": arguments})
            try:
                return future.result(timeout=effective_timeout)
            except concurrent.futures.TimeoutError:
                return {
                    "tool_name": name,
                    "tool_arguments": arguments,
                    "tool_result": None,
                    "truncate": False,
                    "error": f"Error: Tool execution timed out after {effective_timeout} seconds."
                }
            except Exception as e:
                return {
                    "tool_name": name,
                    "tool_arguments": arguments,
                    "tool_result": None,
                    "truncate": False,
                    "error": str(e)
                }

    def generate_prompt(self, name: str, arguments: dict) -> str:
        """Route a prompt generation request to the owning MCP server."""
        server = self._prompt_registry.get(name)
        if server is None:
            raise ValueError(f"Prompt '{name}' is not registered in any MCP server.")
        return server.handle_rpc("prompt_generate", {"name": name, "arguments": arguments})

    def get_identity_prompt(self) -> str:
        """Return the core agent identity prompt."""
        if self.identity_mcp:
            prompt_func = getattr(self.identity_mcp, "identity_prompt", None)
            if prompt_func:
                return prompt_func()
        return ""

    def get_language(self) -> str:
        """Return the configured language from identity MCP."""
        if self.identity_mcp:
            get_lang_func = getattr(self.identity_mcp, "get_language", None)
            if get_lang_func:
                return get_lang_func()
        return "English"
