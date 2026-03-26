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
                
            # Search Knowledge Base RAG
            try:
                from imports.embedding_service import EmbeddingService
                from imports.knowledge_base_rag import KnowledgeBaseRAG
                app_config = self.engine.config
                if app_config and app_config.get("context", {}).get("memory", {}).get("active", False):
                    mem_cfg = app_config["context"]["memory"]
                    emb_service = EmbeddingService.get_instance(
                        emb_model_name=mem_cfg.get("emb_model_name", "intfloat/multilingual-e5-large"),
                        models_cache_path=mem_cfg.get("models_cache_path", "./data/memory/models/")
                    )
                    kb_rag = KnowledgeBaseRAG.get_instance(
                        db_path=mem_cfg.get("db_path", "./data/memory/db/"),
                        embedding_service=emb_service
                    )
                    kb_results = kb_rag.search(query, top_k=3)
                    for kr in kb_results:
                        text = kr.get("text", "")
                        if text:
                            memories.append(f"[KnowledgeBase (score={kr.get('score', 0):.2f})] {text}")
            except Exception as e:
                print(f"KBRAG Search failed: {e}")
        
        parsed["result"]["memories"] = memories
        return parsed
