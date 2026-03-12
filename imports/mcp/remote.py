import requests
from typing import Any
from imports.mcp.base import MCPServer

class RemoteMCPServer(MCPServer):
    """A client interface that wraps a remote MCP server.
    
    Routes RPC calls over HTTP to the specified URL.
    """
    
    def __init__(self, url: str) -> None:
        self.url = url
        
    def handle_rpc(self, method: str, params: dict | None = None) -> Any:
        if params is None:
            params = {}
            
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        
        try:
            response = requests.post(self.url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                raise ValueError(f"Remote server error: {data['error']}")
                
            return data.get("result")
        except Exception as e:
            raise ValueError(f"RPC {method} to {self.url} failed: {e}")
