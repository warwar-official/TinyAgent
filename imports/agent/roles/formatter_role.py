import json
from imports.agent.pipeline.role_base import AIRole

class PersonalityFormatterRole(AIRole):
    name = "PersonalityFormatter"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Formatter role: formats the final response for the user.
        
        Task mode payload: {"raw_answer": str, "input": str, "history": list, "memory": list, "identity": str, "language": str, "media": list, "input_images": list, "system_time": str, "execution_trace": dict}
        Conversation mode payload: {"input": str, "history": list, "memory": list, "identity": str, "language": str, "media": list, "input_images": list, "system_time": str, "execution_trace": dict}
        
        Formatter does NOT have access to: tools, tasks, abilities.
        
        Returns: {"result": {"final_user_message": str}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("formatter_role_prompt", {}) if self.engine.mcp_connector else ""
        raw_answer = payload.get("raw_answer", "")
        language = payload.get("language", "English")
        media = payload.get("media", [])
        input_images = payload.get("input_images", [])
        
        # Use PromptMCP to format the payload
        format_args = {
            "identity": payload.get("identity", ""),
            "trace": payload.get("execution_trace", {}),
            "current_time": payload.get("system_time", ""),
            "memories": payload.get("memory", []),
            "history": payload.get("history", []),
            "user_input": payload.get("input", "")
        }
        
        user_prompt = self.engine.mcp_connector.generate_prompt("format_payload", format_args) if self.engine.mcp_connector else ""
        
        if raw_answer:
            user_prompt += f"\n### Raw Factual Answer to Format\n{raw_answer}\n"
            
        user_prompt += f"\n**Language:** Respond in {language}.\n"
        
        # Notify formatter about generated images
        if media:
            hashes_text = ", ".join(media)
            user_prompt += f"\n> [!NOTE]\n> Images were successfully generated during this task with hashes: {hashes_text}. The system will automatically attach these images to your response. You should acknowledge or describe the image(s) in your reply as if you are sending them.\n"

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            # history_records=payload.get("history", []), # History is now in user_prompt
            input_images=input_images,
        )
        return self.parse_json_response(response_text)
