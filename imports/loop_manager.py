from imports.task_manager import TaskManager
from imports.models.generative.base_model import BaseAPIModel
import json

class LoopManager:
    def __init__(self, model: BaseAPIModel, context_manager: ContextManager, task_manager: TaskManager, tool_table: dict[str, callable]) -> None:
        self.context_manager: ContextManager = context_manager
        self.model: BaseAPIModel = model
        self.tool_table: dict[str, callable] = tool_table
        self.step: int = 0
        self.task_manager: TaskManager = task_manager

        self.last_answer: str = ""

        self.perform_loop(self.context_manager.system_prompt)
        self.perform_system_summary()
    
    def get_last_answer(self) -> str:
        return self.last_answer
    
    def perform_loop(self, initial_prompt: str) -> None:
        self.context_manager.set_current_task(self.task_manager.get_task())
        self.context_manager.retrive_memories(initial_prompt)
        self.context_manager.add_record("user",initial_prompt)
        payload = self.context_manager.make_payload()
        answer = self.model.make_request(payload)
        self.context_manager.add_record("model",answer)
        toolcall = self.context_manager.parse_toolcall(answer)
        self.step += 1
        while toolcall:
            self.step += 1
            self._use_tool(toolcall)
            payload = self.context_manager.make_payload()
            answer = self.model.make_request(payload)
            self.context_manager.add_record("model",answer)
            toolcall = self.context_manager.parse_toolcall(answer)
        if self.step > 10:
            self.step = 0
            self.perform_memory_summary()
            self.perform_summary()
        self.last_answer = self.context_manager._remove_thinking(answer)
    
    def perform_single_call(self, prompt: str) -> str:
        payload = self.context_manager.make_payload()
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
        self.context_manager.conversation_summary = self.context_manager._remove_thinking(self.perform_single_call(summary_prompt))
        self.context_manager.conversation_summary_id = self.context_manager.history.get_records()[-5].id
    
    def perform_system_summary(self) -> None:
        system_summary_prompt = (
            "Please, summarize how you understand your role and instructions.\n"
            "Dont use tools.\n"
            "Dont summarize information about tools."
            )
        self.context_manager.system_summary = self.perform_single_call(system_summary_prompt)
        self.context_manager.conversation_summary = self.context_manager.history.get_records()[-1].message
        self.context_manager.conversation_summary_id = self.context_manager.history.get_records()[-1].id
    
    def perform_memory_summary(self) -> None:
        memory_summary_prompt = (
            "Please, summarize important inforamtion from this conversation that should be remembered.\n"
            "Summarize facts in 1-2 sentences that could be understood without initial context.\n"
            "Dont summarize meaningless, shorttime information like tool execution results, error logs etc.\n"
            "If you found nothing meaningful in coversation, feel free to return empty list.\n"
            "Give answer in JSON format with keys: 'important_facts' (list of strings).\n"
            "Dont use tools.\n"
            "Dont summarize information about tools."
            )
        raw_memory_summary = self.perform_single_call(memory_summary_prompt)
        memory_summary = raw_memory_summary[raw_memory_summary.find("{"):raw_memory_summary.rfind("}") + 1]
        memory_summary_list = json.loads(memory_summary)["important_facts"]
        for fact in memory_summary_list:
            self.context_manager.memory.add_memory(fact)
    
    def _use_tool(self, toolcall: dict) -> None:
        tool_result_template = """[TOOL: {name}] {result} [TOOL_END]"""
        tool_summary_prompt = (
            "Make summary of tool execution result. Extract important information.\n"
            "Extract facts, important links, names, dates etc.\n"
            "Summary should not be longer that 500 tokens.\n"
            "Tool name: {name}, returned result: {result}"
        )
        if toolcall["name"] in self.tool_table:
            result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
            if len(result) > 1000:
                result = self.model.make_request({
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": tool_summary_prompt.format(toolcall["name"], result)
                                }
                            ]
                        }
                    ]
                })
                self.context_manager.add_record("user",tool_result_template.format(name=toolcall["name"], result=result))
            else:
                self.context_manager.add_record("user",tool_result_template.format(name=toolcall["name"], result=result))
        else:
            self.context_manager.add_record("user",tool_result_template.format(name=toolcall["name"], result="Error: Tool not found"))
