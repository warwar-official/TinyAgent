from imports.history_manager import HistoryManager
from imports.models.base_model import BaseAPIModel
import json

class LoopManager:
    def __init__(self, system_prompt: str, model: BaseAPIModel, tool_table: dict[str, callable]) -> None:
        self.history: HistoryManager = HistoryManager()
        self.model: BaseAPIModel = model
        self.system_prompt: str = system_prompt
        self.tool_table: dict[str, callable] = tool_table
        self.conversation_summary: str | None = None
        self.conversation_summary_id: str | None = None
        self.system_summary: str | None = None
        self.step: int = 0

        self.perform_loop(system_prompt)
        self.perform_system_summary()
    
    def perform_loop(self, initial_prompt: str) -> None:
        self._add_record("user",initial_prompt)
        payload = self._make_payload()
        answer = self.model.make_request(payload)
        self._add_record("model",answer)
        toolcall = self._parse_toolcall(answer)
        while toolcall:
            self.step += 1
            self._use_tool(toolcall)
            payload = self._make_payload()
            answer = self.model.make_request(payload)
            self._add_record("model",answer)
            toolcall = self._parse_toolcall(answer)
        if self.step > 10:
            self.step = 0
            self.perform_summary()
    
    def perform_single_call(self, prompt: str) -> str:
        payload = self._make_payload()
        payload['contents'].append({
            'role': "user",
            'parts': [
                {
                    'text': prompt
                }
            ]
        })
        answer = self.model.make_request(payload)
        return answer

    def perform_summary(self) -> None:
        summary_prompt = (
            "Please, summarize the conversation.\n"
            "Dont use tools.\n"
            "Dont summaryze system or identity information. Concentrate on conversation, facts. If you are doing multi-step task now, describe it to be able to continue it."
        )
        self.perform_single_call(summary_prompt)
        self.conversation_summary = self.history.get_records()[-1].message
        self.conversation_summary_id = self.history.get_records()[-1].id
    
    def perform_system_summary(self) -> None:
        system_summary_prompt = (
            "Please, summarize how you understand your role and instructions.\n"
            "Dont use tools.\n"
            "Dont summarize information about tools."
            )
        self.system_summary = self.perform_single_call(system_summary_prompt)
        self.conversation_summary = self.history.get_records()[-1].message
        self.conversation_summary_id = self.history.get_records()[-1].id

    def _make_payload(self) -> dict:
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
        return payload
    
    def _remove_old_tool_results(self) -> None:
        for record in self.history.get_records():
            if record.message.startswith("Tool") and record.role == "user":
                self.history.remove_record(record.id)
    
    def _add_record(self, role: str, message: str) -> None:
        self.history.add_record(role, message)
        print(f"{role}: {message}")

    def _parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{\"toolcall"):message.rfind("}")+1]
            return json.loads(toolcall)["toolcall"]
        else:
            return None
    
    def _use_tool(self, toolcall: dict) -> None:
        tool_result_template = """[TOOL: {name}] {result} [TOOL_END]"""
        #self._remove_old_tool_results()
        if toolcall["name"] in self.tool_table:
            result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
            if len(result) > 1000:
                result = self.model.make_request({
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": f"Make summary of tool execution result. Extract important information. Tool name: {toolcall['name']}, returned result: {result}"
                                }
                            ]
                        }
                    ]
                })
                self._add_record("model",tool_result_template.format(name=toolcall["name"], result=result))
            else:
                self._add_record("model",tool_result_template.format(name=toolcall["name"], result=result))
        else:
            self._add_record("model",tool_result_template.format(name=toolcall["name"], result="Error: Tool not found"))
