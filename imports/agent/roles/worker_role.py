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
            "abilities": list,
            "verification_feedback": str,
        }
        
        Worker does NOT have access to: identity, history, memory, tasks_history.
        
        Returns: {"result": {"action": "tool"|"text"|"ask_user"|"interrupt", "status": "success"|"interrupt", "answer": str, "media": list[str], ...}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("worker_role_prompt", {}) if self.engine.mcp_connector else ""
        current_task = payload.get("current_task", {})
        feedback = payload.get("verification_feedback", "")
        tasks_history = payload.get("tasks_history", [])
        tools = payload.get("tools", [])
        abilities = payload.get("abilities", [])
        
        tools_text = json.dumps(tools, ensure_ascii=False)
        
        user_prompt = f"Current step: {json.dumps(current_task, ensure_ascii=False)}\n"
        user_prompt += f"Available tools:\n{tools_text}\n"
        if tasks_history:
            user_prompt += f"Steps completed so far:\n{json.dumps(tasks_history, indent=2, ensure_ascii=False)}\n\n"
        if abilities:
            user_prompt += f"Your abilities:\n{json.dumps(abilities, ensure_ascii=False)}\n"
        if feedback:
            user_prompt += f"Feedback from Verifier on previous run: {feedback}\n"
            
        user_prompt += "\nIf the task is unexecutable (e.g. no tool for it, impossible constraints), use action 'interrupt', status 'interrupt' and return 'task_unexecutable' as answer."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
