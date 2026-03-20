import json
from imports.agent.pipeline.role_base import AIRole

class TaskDeconstructorRole(AIRole):
    name = "TaskDeconstructor"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Deconstructor role: iterative next-step planner.
        
        Payload: {
            "task_summary": str,
            "abilities": list,
            "tasks_history": list,
            "media": list[str],
        }
        
        Returns one of:
            {"result": {"decision": "next_task", "next_task": {...}}}
            {"result": {"decision": "task_completed"}}
            {"result": {"decision": "task_interrupted", "reason": str}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("deconstructor_role_prompt", {}) if self.engine.mcp_connector else ""
        
        task_summary = payload.get("task_summary", "")
        abilities = payload.get("abilities", [])
        tasks_history = payload.get("tasks_history", [])
        media = payload.get("media", [])
        
        user_prompt = f"Task Summary: {task_summary}\n\n"
        if abilities:
            user_prompt += f"Available Abilities:\n{json.dumps(abilities, ensure_ascii=False)}\n\n"
        if tasks_history:
            user_prompt += f"Steps completed so far:\n{json.dumps(tasks_history, indent=2, ensure_ascii=False)}\n\n"
        if media:
            user_prompt += f"Available media from previous steps: {json.dumps(media, ensure_ascii=False)}\n\n"
        user_prompt += "Determine the next step or conclude the task."
        if len(tasks_history) > 15:
            user_prompt += f"[SYSTEM NOTICE]: tasks_history is too long. Cleanup required."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
