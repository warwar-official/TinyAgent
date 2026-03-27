import json
from imports.agent.pipeline.role_base import AIRole

class WorkerRole(AIRole):
    name = "Worker"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Worker role: executes a single task step.
        
        Payload: {
            "current_task": dict,
            "tools": list,
            "abilities": str,
            "verification_feedback": str,
            "tasks_history": list,
        }
        
        Returns: {"result": {"action": "tool"|"text"|"ask_user"|"summarize_history_range"|"interrupt", "status": "success"|"interrupt", "answer": str, "summary": str, "entry_ids": list, ...}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("worker_role_prompt", {}) if self.engine.mcp_connector else ""
        current_task = payload.get("current_task", {})
        feedback = payload.get("verification_feedback", "")
        tasks_history = payload.get("tasks_history", [])
        tools = payload.get("tools", [])
        abilities = payload.get("abilities", "")
        
        user_prompt = f"### Current Step\n{json.dumps(current_task, ensure_ascii=False)}\n"
        
        if tools:
            user_prompt += f"### Available Tools\n{json.dumps(tools, ensure_ascii=False)}\n"
            
        if tasks_history:
            user_prompt += f"### Completed Steps History (Progress)\n"
            for i, entry in enumerate(tasks_history, 1):
                desc = entry.get("description", "No description")
                res = entry.get("resolution", "unknown")
                user_prompt += f"{i}. **Action:** {desc} → Status: {res}\n"
            user_prompt += "\n"
            
        if abilities:
            user_prompt += f"### Your Abilities\n{abilities}\n"
            
        if feedback:
            user_prompt += f"### Verifier Feedback\n{feedback}\n"
            
        user_prompt += "\nIf the task is unexecutable (e.g. no tool for it, impossible constraints), use action 'interrupt', status 'interrupt' and return 'task_unexecutable' as answer."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
