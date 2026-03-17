import json
from imports.agent.pipeline.role_base import AIRole

class PersonalityFormatterRole(AIRole):
    name = "PersonalityFormatter"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Formatter role: formats the final response for the user.
        
        Task mode payload: {"raw_answer": str, "input": str, "history": list, "memory": list, "identity": str, "language": str, "media": list, "input_images": list}
        Conversation mode payload: {"input": str, "history": list, "memory": list, "identity": str, "language": str, "media": list, "input_images": list}
        
        Formatter does NOT have access to: tools, tasks, abilities.
        
        Returns: {"result": {"final_user_message": str}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("formatter_role_prompt", {}) if self.engine.mcp_connector else ""
        raw_answer = payload.get("raw_answer", "")
        identity = payload.get("identity", "Be helpful and polite.")
        language = payload.get("language", "English")
        history = payload.get("history", [])
        memory = payload.get("memory", [])
        user_input = payload.get("input", "")
        media = payload.get("media", [])
        input_images = payload.get("input_images", [])
        
        #history_text = "\n".join([f"{r.role}: {r.message}" for r in history])
        
        user_prompt = f"Agent Persona / Identity: {identity}\n"
        #user_prompt += f"Recent Conversation History:\n{history_text}\n\n"
        if memory:
            user_prompt += f"Relevant Memories:\n{json.dumps(memory, ensure_ascii=False)}\n\n"
        user_prompt += f"Current User Message: {user_input}\n"
        
        if raw_answer:
            user_prompt += f"Raw Factual Answer to Format:\n{raw_answer}\n"
            
        user_prompt += f"\nRespond in {language}.\n"
        
        # Notify formatter about generated images
        if media:
            hashes_text = ", ".join(media)
            user_prompt += f"\n[SYSTEM NOTICE]: Images were successfully generated during this task with hashes: {hashes_text}. The system will automatically attach these images to your response. You should acknowledge or describe the image(s) in your reply as if you are sending them.\n"

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            history_records=history,
            input_images=input_images,
        )
        return self.parse_json_response(response_text)
