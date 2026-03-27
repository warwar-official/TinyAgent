import json
from imports.agent.pipeline.role_base import AIRole

class VerifierRole(AIRole):
    name = "Verifier"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Verifier role: evaluates a single step result.
        
        Payload: {"task": dict, "worker_output": dict, "answer": dict, "images": list[str]}
        
        Verifier does NOT see: history, identity, memory.
        
        Returns: {"result": {"resolution": "success"|"failure"|"interrupt"}, "notes": str}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("verifier_role_prompt", {}) if self.engine.mcp_connector else ""
        current_step = payload.get("task", {})
        worker_output = payload.get("worker_output", {})
        answer = payload.get("answer", {})
        images = payload.get("images", [])
        identity = payload.get("identity", "")
        
        if not current_step:
            return {"notes": "No current step to verify.", "result": {"resolution": "success"}}
            
        user_prompt = f"### Step Context\n**Step Description:** {json.dumps(current_step, ensure_ascii=False)}\n"
        
        if worker_output:
            user_prompt += f"### Worker Decision\n{json.dumps(worker_output, ensure_ascii=False)}\n"
            status = worker_output.get("status", "success")
            if status == "interrupt":
                user_prompt += "> [!IMPORTANT]\n> The worker interrupted this task because it is unexecutable. Evaluate if this is a valid reason for interruption.\n"
        
        if answer:
            user_prompt += f"### Execution Results\n{json.dumps(answer, ensure_ascii=False)}\n"
        else:
            if not worker_output:
                user_prompt += "> [!NOTE]\n> No tool output or text produced for this step yet.\n"
        
        if images:
            user_prompt += f"**Generated Images:** {json.dumps(images, ensure_ascii=False)}\n"
            
        if identity:
            user_prompt += f"### System Identity (Constraints)\n{identity}\n"

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            input_images=images,
        )
        return self.parse_json_response(response_text)
