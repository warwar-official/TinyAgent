import json
from abc import ABC, abstractmethod

class AIRole(ABC):
    """Base class for all AI roles in the pipeline."""

    name: str = "BaseRole"
    prompt: str = ""

    @abstractmethod
    def run(self, payload: dict) -> dict:
        """
        Executes the role logic utilizing the given payload.
        
        Args:
            payload (dict): The shared state information between roles.
                Expected fields usually include:
                - `input_message`: dict with str/img_hash
                - `task_table`: list of steps
                - `current_step`: int
                - `tool_results`: list
                - `persona`: str
                
        Returns:
            dict: Role execution result. Expected structure for most roles:
                {
                    "notes": "...internal reasoning...",
                    "result": {...}
                }
        """
        pass

    def parse_json_response(self, response_text: str) -> dict:
        """
        Helper method to extract and parse JSON from the model's response.
        """
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx + 1]
                return json.loads(json_str)
            else:
                # Fallback if the model didn't wrap in JSON logic
                return {"notes": "Parsing error", "result": {}, "raw": response_text}
        except json.JSONDecodeError as e:
            return {"notes": f"JSON Decode Error: {e}", "result": {}, "raw": response_text}
