from imports.history_manager import HistoryManager
from imports.plugins.memory_RAG import MemoryRAG
from imports.task_manager import Task
from datetime import datetime
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
        self.current_task: str = "No task"
        self.retrived_memories: str = "No retrived memories"

    def parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{\"toolcall"):message.rfind("}")+1]
            return json.loads(toolcall)["toolcall"]
        else:
            return None

    def add_record(self, role: str, message: str) -> None:
        """if role == "model":
            message = self._remove_thinking(message)"""
        self.history.add_record(role, message)
        print(f"{role}: {message}")
    
    def set_current_task(self, task: Task | None) -> None:
        if task:
            self.current_task = task.name + "\n" + task.description + "\n" + task.priority + "\n"
        else:
            self.current_task = "No task"

    def retrive_memories(self, query: str) -> None:
        if self.memory:
            memories = self.memory.search(query)
            self.retrived_memories = ""
            if memories:
                for memory in memories:
                    self.retrived_memories += memory + "\n"
            else:
                self.retrived_memories = "No retrived memories"
        else:
            self.retrived_memories = "No retrived memories"

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
                        'text': "[SYSTEM]" + self.system_prompt +
                        "\n\n Identity summary: " + self.system_summary + "\n\n" +
                        "[SYSTEM_END]" +
                        "\n\n[RUNTIME_STATE]" +
                        "\n\n Current time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + 
                        "\n\n Current task: " + self.current_task +
                        "\n\n Retrived memories: " + self.retrived_memories +
                        "\n\n" +
                        "[RUNTIME_STATE_END]"
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