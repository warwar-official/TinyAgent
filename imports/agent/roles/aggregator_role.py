import json
from imports.agent.pipeline.role_base import AIRole

class AggregatorRole(AIRole):
    name = "Aggregator"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Aggregator role: combines all task results into a single answer.
        
        Payload: {"task_summary": str, "tasks_history": list, "input_images": list, "media": list}
        
        Returns: {"result": {"answer": str, "images": list[str]}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("aggregator_role_prompt", {}) if self.engine.mcp_connector else ""
        task_summary = payload.get("task_summary", "")
        tasks_history = payload.get("tasks_history", [])
        input_images = payload.get("input_images", [])
        
        # Collect all image hashes from tasks_history
        images = []
        for entry in tasks_history:
            images.extend(entry.get("media", []))
        
        user_prompt = f"User Task Summary: {task_summary}\n\n"
        user_prompt += f"Completed Steps History:\n{json.dumps(tasks_history, indent=2, ensure_ascii=False)}\n"
        if images:
            user_prompt += f"Generated images: {json.dumps(images, ensure_ascii=False)}\n"
        user_prompt += "Please aggregate the findings and provide the definitive final answer. If any steps failed or were interrupted, mention this and explain the impact."

        response_text = self.engine.generate_response(
            role=self,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            input_images=input_images,
        )
        parsed = self.parse_json_response(response_text)
        
        # Inject images into result
        if "result" not in parsed:
            parsed["result"] = {}
        parsed["result"]["images"] = images
        
        return parsed
