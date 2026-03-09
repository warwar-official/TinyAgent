from typing import Any


class MCPServer:
    """Base class for all MCP-compatible servers.

    Subclasses implement `_rpc_<method>` methods, which are dispatched
    automatically by `handle_rpc`.

    Standard RPC methods:
        tool_list, tool_execute, prompt_list, prompt_generate, resource_list
    """

    def handle_rpc(self, method: str, params: dict | None = None) -> Any:
        """Universal JSON-RPC style entry point.

        Looks for a method named ``_rpc_{method}`` on the instance and
        calls it with *params* (defaulting to an empty dict).

        Raises:
            ValueError: If no handler is found for the given *method*.
        """
        if params is None:
            params = {}
        handler = getattr(self, f"_rpc_{method}", None)
        if handler is None:
            raise ValueError(f"Unknown RPC method: {method}")
        return handler(params)
