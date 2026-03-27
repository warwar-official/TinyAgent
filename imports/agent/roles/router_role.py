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
        if not user_prompt:
            # Fallback if MCP fails
            user_prompt = f"User Input: {payload.get('input', '')}"

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            # history_records=payload.get("history", []), # We now include history in the user_prompt
            input_images=payload.get("input_images", []),
        )
        return self.parse_json_response(response_text)
