from imports.history_manager import HistoryManager
from imports.models.base_model import BaseAPIModel
import json

class LoopManager:
    def __init__(self, system_prompt: str, model: BaseAPIModel, tool_table: dict[str, callable]) -> None:
        self.history: HistoryManager = HistoryManager()
        self.model: BaseAPIModel = model
        self.system_prompt: str = system_prompt
        self.tool_table: dict[str, callable] = tool_table

        self.perform_loop(system_prompt)
    
    def perform_loop(self, initial_prompt: str) -> None:
        self._add_record("user",initial_prompt)
        payload = self._make_payload()
        answer = self.model.make_request(payload)
        self._add_record("model",answer)
        toolcall = self._parse_toolcall(answer)
        while toolcall:
            self._use_tool(toolcall)
            payload = self._make_payload()
            answer = self.model.make_request(payload)
            self._add_record("model",answer)
            toolcall = self._parse_toolcall(answer)

    def _make_payload(self) -> dict:
        payload = {
            'contents': [
            ]
        }
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
    
    def _add_record(self, role: str, message: str) -> None:
        self.history.add_record(role, message)
        print(f"{role}: {message}")

    def _parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{"):message.rfind("}")+1]
            return json.loads(toolcall)["toolcall"]
        else:
            return None
    
    def _use_tool(self, toolcall: dict) -> None:
        if toolcall["name"] in self.tool_table:
            result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
            self._add_record("user",f"Tool {toolcall['name']}, returned result: {result}")
        else:
            self._add_record("user",f"Tool {toolcall['name']} not found")
