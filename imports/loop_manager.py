from imports.history_manager import HistoryManager, HistoryRecord
from imports.providers_manager import ProvidersManager, Model
from imports.memory_manager import MemoryManager
from datetime import datetime
import json
import importlib
import re

class LoopManager:
    def __init__(self, config: dict) -> None:
        self.config = config

        self.providers_manager = ProvidersManager(self.config["providers"])
        self.model = Model(**self.config["agent"]["model"])
        self.history_manager = HistoryManager(self.config["context"]["history_path"])
        if self.config["context"]["memory"]["active"]:
            self.memory = MemoryManager(self.config)
        else:
            self.memory = None
        self.retrived_memory = "None"
        self.prompts = self._load_prompts(self.config["context"]["prompts_path"])
        self.state = self._load_state(self.config["context"]["state_path"])

        if self.state["identity"] == "":
            self._identity_setup()
            self._save_state(self.config["context"]["state_path"])
        
        self.tool_table = self._load_tools(self.config)
        self.tool_description = self._make_tool_description(self.config)

    def perform_loop(self, user_input: str) -> None:
        if self.memory:
            self.retrived_memory = self.memory.search(user_input)
            if self.retrived_memory == []:
                self.retrived_memory = "None"
        self.history_manager.add_record("user",user_input)
        payload = self._make_general_payload()
        answer = self.providers_manager.generation_request(self.model, payload)
        self.history_manager.add_record("model",answer)
        print("model:" + answer.strip())
        toolcall = self._parse_toolcall(answer)
        while toolcall:
            self._use_tool(toolcall)
            payload = self._make_general_payload()
            answer = self.providers_manager.generation_request(self.model, payload)
            self.history_manager.add_record("model",answer)
            print("model:" + answer.strip())
            toolcall = self._parse_toolcall(answer)
        if len(self.history_manager.get_records()) > 15:
            self._perform_summary()
            if self.config["context"]["memory"]["active"]:
                self._summaries_memory()
            self.history_manager.set_old_records_mark(5)

    def _perform_summary(self) -> None:
        conversation_summary_prompt = self.prompts["conversation_summary_prompt"]
        payload = self.history_manager.get_records() + [HistoryRecord("user", conversation_summary_prompt)]
        answer = self.providers_manager.generation_request(self.model, payload)
        self.state["conversation_summary"] = self._remove_thinking(answer)
        self._save_state(self.config["context"]["state_path"])
    
    def _summaries_memory(self) -> None:
        memory_symmary_prompt = self.prompts["memory_summary_prompt"]
        payload = self.history_manager.get_records() + [HistoryRecord("user", memory_symmary_prompt)]
        raw_memory_summary = self.providers_manager.generation_request(self.model, payload)
        memory_summary = raw_memory_summary[raw_memory_summary.find("{"):raw_memory_summary.rfind("}") + 1]
        memory_summary_list = json.loads(memory_summary)["important_facts"]
        print("\n" + str(memory_summary_list) + "\n")
        for fact in memory_summary_list:
            if self.memory:
                self.memory.add_memory(fact.strip())

    def _make_general_payload(self) -> list[HistoryRecord]:
        system_prompt = (
            "[SYSTEM]\n\n"
            "# IDENTITY SECTION\n\n"
            f"{self.state['identity']}\n\n"
            "# TECHNICAL SECTION\n\n"
            f"{self.prompts['ability_prompt']}\n\n"
            f"{self.prompts['tools_prompt']}\n"
            f"{self.tool_description}\n\n"
            "# RUNTIME STATE\n\n"
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Retrived memories:\n{self.retrived_memory}\n"
            "[END_SYSTEM]\n"
        )
        system_record = [HistoryRecord("system", system_prompt)]
        if self.state["conversation_summary"] != "":
            system_record.append(HistoryRecord("model", self.state["conversation_summary"]))
        payload = system_record + self.history_manager.get_records()

        return payload

    def _use_tool(self, toolcall: dict) -> None:
        tool_result_template = "[TOOL: {name}] {result} [TOOL_END]"
        tool_summary_prompt = self.prompts["tool_summary_prompt"]
        result = ""
        if toolcall["name"] in self.tool_table:
            result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
            if len(result) > 2500:
                payload = [HistoryRecord("user", tool_summary_prompt.format(toolcall["name"], result))]
                result = self.providers_manager.generation_request(self.model, payload)
            self.history_manager.add_record("tool",tool_result_template.format(name=toolcall["name"], result=result))
        else:
            self.history_manager.add_record("tool",tool_result_template.format(name=toolcall["name"], result="Error: Tool not found"))
        print("tool:" + result.strip())

    def _load_prompts(self, path: str) -> dict:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except IOError as e:
            print(f"Unable to read prompts! Error: {e}")
        except json.JSONDecodeError as e:
            print(f"Unable to decode prompts! Error: {e}")
        return {}

    def _load_state(self, path: str) -> dict:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except IOError as e:
            print(f"Unable to read state! Error: {e}")
        except json.JSONDecodeError as e:
            print(f"Unable to decode state! Error: {e}")
        return self.init_state()
    
    def _save_state(self, path: str) -> None:
        try:
            with open(path, "w") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=4)
        except IOError as e:
            print(f"Unable to write state! Error: {e}")
    
    def init_state(self) -> dict:
        return {
            "identity": "",
            "conversation_summary": ""
        }
    
    def _identity_setup(self) -> None:
        print("Identity setup started...")
        self.history_manager.add_record("user",self.prompts["initial_prompt"])
        payload = self.history_manager.get_records()
        answer = self.providers_manager.generation_request(self.model, payload)
        self.history_manager.add_record("model",answer)
        print("model:" + answer.strip())
        while True:
            user_input = input("Enter your message: ")
            if user_input == "/bye":
                break
            self.history_manager.add_record("user",user_input)
            payload = self.history_manager.get_records()
            answer = self.providers_manager.generation_request(self.model, payload)
            self.history_manager.add_record("model",answer)
            toolcall = self._parse_toolcall(answer)
            if toolcall:
                if toolcall["name"] == "update_identity":
                    identity = toolcall["arguments"]["identity"]
                    self.history_manager.wipe_history()
                    self.history_manager.add_record("model",identity)
                    self.history_manager.add_record("user",self.prompts["character_setup_prompt"])
                    payload = self.history_manager.get_records()
                    answer = self.providers_manager.generation_request(self.model, payload)
                    self.state["identity"] = answer
                    self.history_manager.wipe_history()
                    print("Identity setup complete. Starting conversation...")
                    break
                else:
                    print(f"Unknown toolcall: {toolcall['name']}")
            print("model:" + answer.strip())
    
    def _parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{\"toolcall"):message.rfind("}")+1]
            return json.loads(toolcall)["toolcall"]
        return None
    
    def _load_tools(self, config: dict) -> dict:
        tool_table = {}
        try:
            for tool in config["tools"]:
                tool_name = tool["name"]
                module = importlib.import_module(f"imports.tools.{tool_name}")
                tool_table[tool_name] = getattr(module, tool_name)
        except json.JSONDecodeError as e:
            print(f"Unable to decode config! Error: {e}")
        return tool_table

    def _make_tool_description(self, config: dict) -> str:
        prompt = ""
        for tool in config["tools"]:
            prompt += f"\n{tool['name']}: {tool['description']}\nParameters: {tool['parameters']}\n"
        return prompt
    
    def _remove_thinking(self, message: str) -> str:
        return re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL)