from imports.history_manager import HistoryManager
from imports.models.base_model import BaseAPIModel

class LoopManager:
    def __init__(self) -> None:
        self.history: HistoryManager = HistoryManager()
        self.model: BaseAPIModel | None = None
        self.system_prompt: str = ""
        self.tool_table: dict[str, callable] = {}

    def set_model(self, model: BaseAPIModel) -> None:
        self.model = model

    def set_system_prompt(self, prompt: str) -> None:
        self.sys_prompt = prompt
    
    def set_tool_table(self, tool_table: dict[str, callable]) -> None:
        self.tool_table = tool_table
    
    def perform_loop(self, initial_prompt: str) -> None:
        self.history.add_record("user",initial_prompt)
        payload = self._make_payload()
        answer = self.model.make_request(payload)
        self.history.add_record("model",answer)
        toolcall = self.parse_toolcall(answer)
        while toolcall:
            self.use_tool(toolcall)
            payload = self._make_payload()
            answer = self.model.make_request(payload)
            self.history.add_record("model",answer)
            toolcall = self.parse_toolcall(answer)

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
        for role, text in self.history.get_records():    
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
    
    def use_tool(self, toolcall: dict) -> None:
        if toolcall["name"] in self.tool_table:
            result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
            self.history.add_record("user",f"Tool {toolcall['name']}, arguments: {toolcall['arguments']}, returned result: {result}")
        else:
            self.history.add_record("user",f"Tool {toolcall['name']} not found")
