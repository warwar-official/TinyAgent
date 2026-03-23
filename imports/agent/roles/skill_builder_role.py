import json
from imports.agent.pipeline.role_base import AIRole

class SkillBuilderRole(AIRole):
    name = "SkillBuilder"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        SkillBuilder role: extracts a reusable skill from a completed task execution.
        
        Payload: {
            "task_summary": str,
            "tasks_history": list,
            "input_images": list[str],
            "media": list[str],
        }
        
        Returns: {
            "result": {
                "save_skill": true|false,
                "skill": {
                    "task_signature": str,
                    "steps": list,
                    "successful_path": list,
                    "failed_paths": list,
                    "notes": str
                }
            }
        }
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("skill_builder_role_prompt", {}) if self.engine.mcp_connector else ""
        
        task_summary = payload.get("task_summary", "")
        tasks_history = payload.get("tasks_history", [])
        media = payload.get("media", [])
        
        user_prompt = f"Task Summary: {task_summary}\n\n"
        if tasks_history:
            user_prompt += f"Execution History:\n{json.dumps(tasks_history, indent=2, ensure_ascii=False)}\n\n"
        if media:
            user_prompt += f"Generated media: {json.dumps(media, ensure_ascii=False)}\n\n"
        user_prompt += "Analyze this execution and extract a reusable skill if applicable."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
