import json
from imports.agent.pipeline.role_base import AIRole

class MemoryCreationRole(AIRole):
    name = "MemoryCreation"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Memory Creator role: decides whether to memorize something from history.
        
        Payload: {"history": list[HistoryRecord]}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("memory_creation_role_prompt", {}) if self.engine.mcp_connector else ""
        history_records = payload.get("history", [])
        if not history_records:
            return {"create_memory": False}
            
        recent_history = history_records[-5:]#[r.to_dict() for r in history_records[-5:]]
        
        #user_prompt = f"Recent Conversation:\n{json.dumps(recent_history, indent=2, ensure_ascii=False)}\n\n"
        user_prompt = "Analyze the conversation and extract long-term memory if needed."
        
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
                user_prompt=user_prompt,
                history_records=recent_history
            )
            parsed = self.parse_json_response(response_text)
        finally:
            self.engine.model = original_model
        
        if parsed.get("create_memory") and parsed.get("memory"):
            if self.engine.mcp_connector:
                mem_data = parsed["memory"]
                content = mem_data.get("content", "")
                mem_type = mem_data.get("type", "fact")
                context = mem_data.get("context", "")
                
                if content:
                    try:
                        self.engine.mcp_connector.execute_tool("save_memory", {
                            "content": content,
                            "context": context,
                            "source": "conversation",
                            "type": mem_type
                        })
                    except Exception as e:
                        parsed["notes"] = f"Failed to save memory: {e}"
                        
        return parsed
