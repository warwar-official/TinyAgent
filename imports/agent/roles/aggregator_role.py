import json
from imports.agent.pipeline.role_base import AIRole

class AggregatorRole(AIRole):
    name = "Aggregator"

    def __init__(self, engine):
        self.engine = engine

    def run(self, payload: dict) -> dict:
        """
        Aggregator role: combines all task results into a single answer.
        
        Payload: {"input": str, "task_results": list, "task_table": list, "input_images": list, "media": list}
        
        Returns: {"result": {"answer": str, "images": list[str]}}
        """
        SYSTEM_PROMPT = self.engine.mcp_connector.generate_prompt("aggregator_role_prompt", {}) if self.engine.mcp_connector else ""
        task_summary = payload.get("task_summary", "")
        task_results = payload.get("task_results", [])
        task_table = payload.get("task_table", [])
        input_images = payload.get("input_images", [])
        
        # Collect all image hashes from task results
        images = []
        for r in task_results:
            images.extend(r.get("images", []))
        
        user_prompt = f"User Task Summary: {task_summary}\n\n"
        user_prompt += f"Task Steps and Statuses:\n{json.dumps(task_table, indent=2, ensure_ascii=False)}\n"
        user_prompt += f"Execution Results:\n{json.dumps(task_results, indent=2, ensure_ascii=False)}\n"
        if images:
            user_prompt += f"Generated images: {json.dumps(images, ensure_ascii=False)}\n"
        user_prompt += "Please aggregate the findings and provide the definitive final answer. If any steps failed (status=failed), mention this and explain why they were skipped based on execution results or retries."

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
