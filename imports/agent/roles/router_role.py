from imports.agent.pipeline.role_base import AIRole

class RouterRole(AIRole):
    name = "Router"
    
    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Router role: determines request type (conversation vs task).
        
        Payload: {"input": str, "history": list, "identity": str, "memory": list, "input_images": list}
        Returns: {"result": {"type": "conversation" | "task"}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("router_role_prompt", {}) if self.engine.mcp_connector else ""
        user_input = payload.get("input", "")
        identity = payload.get("identity", "")
        history = payload.get("history", [])
        memory = payload.get("memory", [])
        input_images = payload.get("input_images", [])

        #history_text = "\n".join([f"{r.role}: {r.message} , image: {r.image_hashes}" for r in history])
        
        user_prompt = f"Agent Identity / Rules:\n{identity}\n\n"
        #user_prompt += f"Recent Conversation History:\n{history_text}\n\n"
        if memory:
            user_prompt += f"Relevant Memories:\n{memory}\n\n"
        user_prompt += f"User Input: {user_input}\n"
        
        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            history_records=history,
            input_images=input_images,
        )
        return self.parse_json_response(response_text)
