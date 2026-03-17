import json
from imports.agent.pipeline.role_base import AIRole

class SummaryRole(AIRole):
    name = "Summary"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict, history_manager=None) -> dict:
        """
        Summary Creator role: creates a summary from conversation history.
        
        Payload: {"history": list[HistoryRecord]}
        """
        if not history_manager:
            return {"status": "skipped, no history manager"}
            
        records = history_manager.get_dialog_records()
        if len(records) < 20:
             return {"status": f"skipped, {len(records)} < 20 records"}
             
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("summary_role_prompt", {}) if self.engine.mcp_connector else ""
        records_text = [r.to_dict() for r in records]
        user_prompt = f"Conversational History to summarize:\n{json.dumps(records_text, indent=2, ensure_ascii=False)}"
        
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
            )
            parsed = self.parse_json_response(response_text)
            summary_text = parsed.get("summary", "")
            
            if summary_text:
                history_manager.compress_dialog_history(summary_text, keep_recent=5)
                
            return parsed
        finally:
            self.engine.model = original_model
