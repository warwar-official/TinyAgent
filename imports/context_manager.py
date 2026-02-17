from imports.history_manager import HistoryManager
from imports.plugins.memory_RAG import MemoryRAG
import json
import re

class ContextManager:
    def __init__(self, system_prompt: str, memory: MemoryRAG | None = None):
        self.history = HistoryManager()
        self.memory = memory
        self.system_prompt: str = system_prompt
        self.conversation_summary: str | None = None
        self.conversation_summary_id: str | None = None
        self.system_summary: str | None = None

    def parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{\"toolcall"):message.rfind("}")+1]
            return json.loads(toolcall)["toolcall"]
        else:
            return None

    def add_record(self, role: str, message: str) -> None:
        self.history.add_record(role, message)
        print(f"{role}: {message}")

    def make_payload(self) -> dict:
        payload = {
            'contents': [
            ]
        }
        if self.system_summary:
            payload['contents'].append({
                'role': "user",
                'parts': [
                    {
                        'text': "[SYSTEM]" + self.system_prompt + "\n\n Identity summary: " + self.system_summary + "[SYSTEM_END]"
                    }
                ]
            })
        if self.conversation_summary:
            payload['contents'].append({
                'role': "model",
                'parts': [
                    {
                        'text': self.conversation_summary
                    }
                ]
            })
        if self.conversation_summary_id:
            is_new_message = False
        else:
            is_new_message = True
        for record in self.history.get_records():
            if record.id == self.conversation_summary_id:
                is_new_message = True
                continue
            elif is_new_message:
                payload['contents'].append({
                    'role': record.role,
                    'parts': [
                        {
                            'text': record.message
                        }
                    ]
                })
        with open("payloads_log.json", "a") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
            f.write(",\n")
        return payload
    
    def _remove_thinking(self, message: str) -> str:
        return re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL)