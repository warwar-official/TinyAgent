from imports.agent.pipeline.role_base import AIRole

class MemoryRetrievalRole(AIRole):
    name = "MemoryRetrieval"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Retriever role: receives ONLY input, performs memory search.
        
        Payload: {"input": str}
        Returns: {"result": {"memories": [...]}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("memory_retrieval_role_prompt", {}) if self.engine.mcp_connector else ""
        user_input = payload.get("input", "")
        
        # We can use summary_model if available, but default model is fine
        summary_model = self.engine.config.get("agent", {}).get("summary_model")
        original_model = self.engine.model
        
        if summary_model:
            from imports.providers_manager import Model
            self.engine.model = Model(**summary_model)
            
        try:
            response_text = self.engine.generate_response(
                role=self,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_input,
            )
            parsed = self.parse_json_response(response_text)
        finally:
            self.engine.model = original_model
        
        action = parsed.get("result", {}).get("action", "skip")
        query = parsed.get("result", {}).get("query", "")
        
        memories = []
        if action == "search" and query and self.engine.mcp_connector:
            try:
                res = self.engine.mcp_connector.execute_tool("search_memory", {"query": query, "limit": 5})
                if isinstance(res, dict) and "results" in res:
                    memories = res["results"]
            except Exception as e:
                parsed["notes"] = f"Memory search failed: {e}"
        
        parsed["result"]["memories"] = memories
        return parsed
