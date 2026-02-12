from imports.history_manager import HistoryManager
from imports.models.base_model import BaseAPIModel

class LoopManager:
    def __init__(self) -> None:
        self.history: HistoryManager = HistoryManager()
        self.model: BaseAPIModel | None = None
        self.system_prompt: str = ""

    def set_model(self, model: BaseAPIModel) -> None:
        self.model = model

    def set_system_prompt(prompt: str) -> None:
        self.sys_prompt = prompt
    
    def perform_loop(self, initial_prompt: str) -> None:
        self.history.add_record("user",initial_prompt)
        answer = self.model.make_request()

    def _make_payload(self) -> dict:
        payload = {
        'contents': [
        ]
    }
    payload['contents'].append({
            'role': 'user',
            'parts': [
                {
                    'text': self.system_prompt
                }
            ]
        })
    for role, text in history:    
        payload['contents'].append({
            'role': role,
            'parts': [
                {
                    'text': text
                }
            ]
        })
    return payload
    
    def parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{"):message.rfind("}")+1]
            return json.loads(toolcall)["toolcall"]
        else:
            return None
    
