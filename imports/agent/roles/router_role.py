from imports.agent.pipeline.role_base import AIRole

class RouterRole(AIRole):
    name = "Router"
    
    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Router role: determines request type (conversation vs task).
        
        Payload: {"input": str, "history": list, "identity": str, "memory": list, "input_images": list, "system_time": str, "execution_trace": dict}
        Returns: {"result": {"type": "conversation" | "task"}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("router_role_prompt", {}) if self.engine.mcp_connector else ""
        user_input = payload.get("input", "")
        identity = payload.get("identity", "")
        history = payload.get("history", [])
        memory = payload.get("memory", [])
        input_images = payload.get("input_images", [])
        system_time = payload.get("system_time", "")
        execution_trace = payload.get("execution_trace", {})

        #history_text = "\n".join([f"{r.role}: {r.message} , image: {r.image_hashes}" for r in history])
        
        import json
        user_prompt = f"Agent Identity / Rules:\n{identity}\n\n"
        user_prompt += f"System Time: {system_time}\n"
        if execution_trace and execution_trace.get("tasks"):
            user_prompt += f"Recent Tasks Execution Trace (to understand recent context):\n{json.dumps(execution_trace, ensure_ascii=False, indent=2)}\n\n"
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
