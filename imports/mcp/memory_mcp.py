from imports.mcp.base import MCPServer
from imports.memory_rag import MemoryRAG

class MemoryMCP(MCPServer):
    def __init__(self, app_config: dict = None, memory_rag: MemoryRAG = None):
        super().__init__()
        if memory_rag:
            self.memory_rag = memory_rag
        elif app_config and app_config.get("context", {}).get("memory", {}).get("active", False):
            self.memory_rag = MemoryRAG(app_config)
        else:
            self.memory_rag = None

    def _rpc_tool_execute(self, params: dict) -> dict:
        if not self.memory_rag:
            return {"status": "error", "message": "Memory system is disabled in config"}
            
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        if tool_name == "save_memory":
            memory_text = args.get("content", "")
            source = args.get("source", "autonomous")
            memory_type = args.get("type", "fact")
            context = args.get("context", "")
            self.memory_rag.add_memory(memory_text, source=source, memory_type=memory_type, context=context)
            return {"status": "success", "message": "Memory saved"}
        elif tool_name == "search_memory":
            query = args.get("query", "")
            limit = min(args.get("limit", 5), 5)  # Enforce max 5
            results = self.memory_rag.search(query, limit=limit)
            
            # Formulate results with max 300 chars per result
            truncated_results = []
            for res in results:
                content = str(res)
                if len(content) > 300:
                    content = content[:297] + "..."
                truncated_results.append(content)
            
            return {"results": truncated_results}
        elif tool_name == "delete_memory":
            return {"status": "error", "message": "Not implemented"}
        elif tool_name == "save_archived_message":
            user_msg = args.get("user_msg", "")
            model_msg = args.get("model_msg", "")
            self.memory_rag.add_archived_message(user_msg, model_msg)
            return {"status": "success", "message": "Archived message saved"}
        elif tool_name == "search_archived_messages":
            query = args.get("query", "")
            limit = min(args.get("limit", 2), 5)
            results = self.memory_rag.search_archived_messages(query, limit=limit)
            return {"results": results}
        else:
            raise ValueError(f"MemoryMCP: Unknown tool {tool_name}")
