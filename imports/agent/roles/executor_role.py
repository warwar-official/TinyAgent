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

        user_prompt = f"### Task Context\n**Task Summary:** {task_summary}\n"

        if abilities:
            user_prompt += f"### Your Abilities\n{abilities}\n"

        if tools:
            user_prompt += f"### Available Tools\n{json.dumps(tools, ensure_ascii=False)}\n"

        if relevant_skills:
            user_prompt += f"### Relevant Skills (Reference Only)\n"
            for i, skill in enumerate(relevant_skills, 1):
                user_prompt += f"{i}. **Skill:** {skill.get('task_signature', 'Unknown')}\n"
            user_prompt += "\n"

        if tasks_history:
            user_prompt += f"### Recent Execution Steps (Last {len(tasks_history)})\n"
            for i, entry in enumerate(tasks_history, 1):
                desc = entry.get("description", "No description")
                res = entry.get("resolution", "unknown")
                result_data = entry.get("result", {})
                user_prompt += f"{i}. **Action:** {desc}\n   → Status: {res}\n"
                if result_data:
                    # Truncate result data if it's too long
                    res_str = json.dumps(result_data, ensure_ascii=False)
                    if len(res_str) > 500:
                        res_str = res_str[:500] + "... [TRUNCATED]"
                    user_prompt += f"   → Result: {res_str}\n"
            user_prompt += "\n"

        if media:
            user_prompt += f"**Available Media:** {json.dumps(media, ensure_ascii=False)}\n"

        if verification_feedback:
            user_prompt += f"### Verifier Feedback\n{verification_feedback}\n"

        if tasks_history and len(tasks_history) > 8:
            user_prompt += "> [!IMPORTANT]\n> `tasks_history` is getting long. Consider using `summarize_history_range` to clean it up.\n"

        user_prompt += "\nAnalyze the current state and choose ONE action, or conclude the task."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return self.parse_json_response(response_text)
