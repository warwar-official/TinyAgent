import json
from imports.agent.pipeline.role_base import AIRole

class HistoryCompressorRole(AIRole):
    name = "HistoryCompressor"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        HistoryCompressor role: Compresses a single long history entry.
        
        Payload: {
            "entry": dict,
            "instruction": str
        }
        
        Returns: {"notes": str, "result": {"compressed_text": str}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("history_compressor_role_prompt", {}) if self.engine.mcp_connector else ""
        
        entry = payload.get("entry", {})
        instruction = payload.get("instruction", "")
        
        user_prompt = f"Target History Entry:\n{json.dumps(entry, indent=2, ensure_ascii=False)}\n\n"
        if instruction:
            user_prompt += f"Specific compression instruction: {instruction}\n"
            
        user_prompt += "Please compress this entry, preserving ALL essential facts, dates, names, links, and data, but removing noise and formatting overhead."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
