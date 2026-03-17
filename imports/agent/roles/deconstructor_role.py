import json
from imports.agent.pipeline.role_base import AIRole

class TaskDeconstructorRole(AIRole):
    name = "TaskDeconstructor"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Deconstructor role: breaks task into steps.
        
        Payload: {"input": str, "history": list, "memory": list, "input_images": list}
        Returns: {"result": {"steps": [...]}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("deconstructor_role_prompt", {}) if self.engine.mcp_connector else ""
        
        task_summary = payload.get("task_summary", "")
        abilities = payload.get("abilities", [])
        
        user_prompt = f"Task Summary: {task_summary}\n\n"
        if abilities:
            user_prompt += f"Available Abilities:\n{json.dumps(abilities, ensure_ascii=False)}\n\n"
        user_prompt += "Break this down into steps."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
