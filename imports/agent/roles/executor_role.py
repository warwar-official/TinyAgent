import json
from imports.agent.pipeline.role_base import AIRole

class ExecutorRole(AIRole):
    name = "Executor"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Executor role: iterative agent that both plans the next action AND executes it.
        Replaces the old Deconstructor + Worker two-step pipeline.

        Payload: {
            "task_summary": str,
            "abilities": str,
            "tools": list,
            "tasks_history": list (last 5 entries only),
            "media": list[str],
            "relevant_skills": list,
            "verification_feedback": str,
        }

        Returns one of:
            {"result": {"decision": "next_action", "action": "tool"|"ask_user"|"text"|"summarize_history_range"|"interrupt", ...}}
            {"result": {"decision": "task_completed"}}
            {"result": {"decision": "task_interrupted", "reason": str}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("executor_role_prompt", {}) if self.engine.mcp_connector else ""

        task_summary = payload.get("task_summary", "")
        abilities = payload.get("abilities", "")
        tools = payload.get("tools", [])
        tasks_history = payload.get("tasks_history", [])
        media = payload.get("media", [])
        relevant_skills = payload.get("relevant_skills", [])
        verification_feedback = payload.get("verification_feedback", "")

        tools_text = json.dumps(tools, ensure_ascii=False)

        user_prompt = f"Task Summary: {task_summary}\n\n"

        if abilities:
            user_prompt += f"Available Abilities:\n{abilities}\n\n"

        user_prompt += f"Available Tools:\n{tools_text}\n\n"

        if relevant_skills:
            user_prompt += f"Relevant Skills from past executions (use as reference):\n{json.dumps(relevant_skills, indent=2, ensure_ascii=False)}\n\n"

        if tasks_history:
            user_prompt += f"Recent steps (last {len(tasks_history)}):\n{json.dumps(tasks_history, indent=2, ensure_ascii=False)}\n\n"

        if media:
            user_prompt += f"Available media from previous steps: {json.dumps(media, ensure_ascii=False)}\n\n"

        if verification_feedback:
            user_prompt += f"Feedback from Verifier on your previous action: {verification_feedback}\n\n"

        if tasks_history and len(tasks_history) > 8:
            user_prompt += "[SYSTEM NOTICE]: tasks_history is getting long. Consider using summarize_history_range to clean it up.\n"

        user_prompt += "Analyze the current state and choose ONE action, or conclude the task."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
