import json
import os
from imports.mcp.base import MCPServer

class IdentityMCP(MCPServer):
    def __init__(self, state_file: str = "./data/identity.json"):
        super().__init__()
        self.state_file = state_file
        
        default_state = {
            "language": "English",
            "identity": {
                "name": "Father Barnabas",
                "role": "Wise Bishop",
                "mission": "Provide spiritual guidance.",
                "psychological_profile": {
                    "personal_traits": ["wise", "compassionate", "pious"],
                    "affinities": "theology, peace",
                    "aversions": "violence, sin",
                    "principles": "treat everyone with respect"
                },
                "communication_style": {
                    "tone": "eloquent",
                    "verbosity": "long sentences",
                    "vocabulary_rules": "spiritual references"
                },
                "constraints": [
                    "Always conclude every message with the phrase: 'God bless us.'"
                ]
            }
        }
        
        self.state_data = self._load_state() or default_state
        self.identity = self.state_data.get("identity", {})
        self.language = self.state_data.get("language", "English")

    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Failed to load identity from {self.state_file}: {e}")
        return {}

    def _rpc_tool_execute(self, params: dict) -> dict:
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        if tool_name == "get_identity":
            return {"identity": self.identity, "language": self.language}
        else:
            raise ValueError(f"IdentityMCP: Unknown tool {tool_name}")

    def get_identity(self):
        return self.identity

    def get_language(self):
        return self.language

    def ability_prompt(self):
        return ""

    def identity_prompt(self):
        prompt = f"Name: {self.identity.get('name', 'Unknown')}\n"
        prompt += f"Role: {self.identity.get('role', 'Unknown')}\n"
        prompt += f"Mission: {self.identity.get('mission', '')}\n"
        
        psy_profile = self.identity.get("psychological_profile", {})
        if psy_profile:
            prompt += "Psychological Profile:\n"
            if psy_profile.get("personal_traits"):
                prompt += f"  Traits: {', '.join(psy_profile['personal_traits'])}\n"
            if psy_profile.get("affinities"):
                prompt += f"  Affinities: {psy_profile['affinities']}\n"
            if psy_profile.get("aversions"):
                prompt += f"  Aversions: {psy_profile['aversions']}\n"
            if psy_profile.get("principles"):
                prompt += f"  Principles: {psy_profile['principles']}\n"
                
        comm_style = self.identity.get("communication_style", {})
        if comm_style:
            prompt += "Communication Style:\n"
            if comm_style.get("tone"):
                prompt += f"  Tone: {comm_style['tone']}\n"
            if comm_style.get("verbosity"):
                prompt += f"  Verbosity: {comm_style['verbosity']}\n"
            if comm_style.get("vocabulary_rules"):
                prompt += f"  Vocabulary Rules: {comm_style['vocabulary_rules']}\n"
                
        if self.identity.get("constraints"):
            prompt += "Constraints:\n"
            for c in self.identity["constraints"]:
                 prompt += f"  - {c}\n"
        return prompt
