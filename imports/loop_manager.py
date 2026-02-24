from imports.history_manager import HistoryManager, HistoryRecord
from imports.providers_manager import ProvidersManager, Model
from imports.memory_manager import MemoryManager
from datetime import datetime, timedelta
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

    def perform_loop(self, user_input: str) -> str:
        self._retrive_memory(user_input)

        self.history_manager.add_record("user",user_input)
        payload = self._make_payload()
        answer = self.providers_manager.generation_request(self.model, payload)
        self.history_manager.add_record("model",answer)
        print("model:" + answer.strip())
        toolcall = self._parse_toolcall(answer)
        while toolcall:
            tool_result = self._use_tool(toolcall)
            self.history_manager.add_record("tool",self.prompts["tool_result_template"].format(name=toolcall["name"], result=tool_result))
            payload = self._make_payload()
            answer = self.providers_manager.generation_request(self.model, payload)
            self.history_manager.add_record("model",answer)
            toolcall = self._parse_toolcall(answer)
        if len(self.history_manager.get_records()) > 15:
            self._summarise()
        return self._remove_thinking(answer.strip())

    def _summarise(self) -> None:
        conversation_summary_prompt = self.prompts["conversation_summary_prompt"]
        prev_records = self.history_manager.get_records()
        if len(prev_records) < 7:
            print("Not enough records to summarise.")
            return
        payload = prev_records + [HistoryRecord("user", conversation_summary_prompt)]
        answer = self.providers_manager.generation_request(self.model, payload)
        self.state["conversation_summary"] = self._remove_thinking(answer)
        self._save_state(self.config["context"]["state_path"])

        if self.config["context"]["memory"]["active"]:
            memory_symmary_prompt = self.prompts["memory_summary_prompt"]
            payload = self.history_manager.get_records() + [HistoryRecord("user", memory_symmary_prompt)]
            raw_memory_summary = self.providers_manager.generation_request(self.model, payload)
            memory_summary = raw_memory_summary[raw_memory_summary.find("{"):raw_memory_summary.rfind("}") + 1]
            memory_summary_list = json.loads(memory_summary)["important_facts"]
            print("\n" + str(memory_summary_list) + "\n")
            for fact in memory_summary_list:
                if self.memory:
                    self.memory.add_memory(fact.strip())
        self.history_manager.set_old_records_mark(5)

    def _retrive_memory(self, user_input: str) -> None:
        if self.memory:
            self.retrived_memory = self.memory.search(user_input)
            if self.retrived_memory == []:
                self.retrived_memory = "None"

    def _make_payload(self, tool: bool = True, ability: bool = True, history: bool = True) -> list[HistoryRecord]:
        if tool:
            tool_description = self.tool_description
        else:
            tool_description = ""
        if ability:
            ability_description = self.prompts["ability_prompt"]
        else:
            ability_description = ""
        last_message_time = self.history_manager.get_records(1)[0].create_time
        if last_message_time:
            time_diff = datetime.now() - last_message_time
            if time_diff < timedelta(minutes=1):
                last_message_time_str = f"{time_diff.seconds // 60} minutes ago"
            elif time_diff < timedelta(hours=1):
                last_message_time_str = f"{time_diff.seconds // 3600} hours ago"
            elif time_diff < timedelta(days=1):
                last_message_time_str = f"{time_diff.days} days ago"
            else:
                last_message_time_str = f"{time_diff.days // 30} months ago"
        else:
            last_message_time_str = "No previous messages"
        system_prompt = (
            "[SYSTEM]\n\n"
            "# IDENTITY SECTION\n\n"
            f"{self.state['identity']}\n\n"
            "# TECHNICAL SECTION\n\n"
            f"{ability_description}\n\n"
            f"{self.prompts['tools_prompt']}\n"
            f"{tool_description}\n\n"
            "# RUNTIME STATE\n\n"
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Last message from user: {last_message_time_str} ago\n"
            f"Retrived memories:\n{self.retrived_memory}\n"
            f"Notes from the autonomus loop:\n{self.state['autonomuse_notes']}\n"
            "[END_SYSTEM]\n"
        )
        system_record = [HistoryRecord("system", system_prompt)]
        if self.state["conversation_summary"] != "":
            system_record.append(HistoryRecord("model", self.state["conversation_summary"]))
        if history:
            payload = system_record + self.history_manager.get_records()
        else:
            payload = system_record
        return payload

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
        return self._init_state()
    
    def _save_state(self, path: str) -> None:
        try:
            with open(path, "w") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=4)
        except IOError as e:
            print(f"Unable to write state! Error: {e}")
    
    def _init_state(self) -> dict:
        return {
            "identity": "",
            "conversation_summary": "",
            "autonomuse_notes": ""
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
    
    def autonomus_loop(self) -> None:
        print("Autonomus loop started...")
        self._summarise()
        self._retrive_memory("It is your automonus turn. Make a decision about your next actions.")
        payload = self._make_payload(tool=False, history=False)
        payload.append(HistoryRecord("system", self.prompts["autonomus_prompt"]))
        answer = self.providers_manager.generation_request(self.model, payload)
        payload.append(HistoryRecord("model", answer))
        print("model:" + answer.strip())
        toolcall = self._parse_toolcall(answer)
        if toolcall:
            if toolcall["name"] == "rethink":
                self._rethink()
            elif toolcall["name"] == "task":
                self._task()
            elif toolcall["name"] == "skip":
                prompt = self.prompts["autonomous_finish_prompt"].format(task="skip this turn")
                payload.append(HistoryRecord("user", prompt))
                answer = self.providers_manager.generation_request(self.model, payload)
                print("model:" + answer.strip())
                self.state["autonomuse_notes"] = answer
            else:
                print(f"Unknown toolcall: {toolcall['name']}")
        
        with open("autonomous_notes.ndjson", "a") as f:
            json.dump({"note" : self.state["autonomuse_notes"]}, f, ensure_ascii=False)
            f.write("\n")
    
    def _rethink(self) -> None:
        print("Rethinking...")
        self._retrive_memory("It is time to rethink your identity and goals. Who are you? What are your goals? What are your relationships with user?")
        payload = self._make_payload(tool=False, history=False)
        payload.append(HistoryRecord("system", self.prompts["autonomus_rethink_prompt"]))
        answer = self.providers_manager.generation_request(self.model, payload)
        self.state["identity"] = self._remove_thinking(answer).strip()
        payload.append(HistoryRecord(role="model",message=answer))
        prompt = self.prompts["autonomous_finish_prompt"].format(task="identity rethinking")
        payload.append(HistoryRecord(role="user",message=prompt))
        answer = self.providers_manager.generation_request(self.model, payload)

        self.state["autonomuse_notes"] = self._remove_thinking(answer).strip()
        self._save_state(self.config["context"]["state_path"])
    
    def _task(self) -> None:
        print("Tasking...")
        answer = "It is turn to make your own task. What do you want to do?"
        autonomus_history = HistoryManager()
        payload = []
        for i in range(15):
            self._retrive_memory(answer)
            payload = self._make_payload(history=False)
            payload.append(HistoryRecord(role="user", message=self.prompts["autonous_task_prompt"]))
            payload.extend(autonomus_history.get_records())
            answer = self.providers_manager.generation_request(self.model, payload)
            autonomus_history.add_record("model",answer)
            print("model:" + answer.strip())
            cleaned_answer = self._remove_thinking(answer.strip().strip("\n"))
            if "[DONE]" in cleaned_answer:
                payload = self._make_payload(tool=False, history=False)
                payload.append(HistoryRecord(role="user", message=self.prompts["autonous_task_prompt"]))
                break
            toolcall = self._parse_toolcall(cleaned_answer)
            if toolcall:
                tool_result = self._use_tool(toolcall)
                autonomus_history.add_record("tool",self.prompts["tool_result_template"].format(name=toolcall["name"], result=tool_result))
            else:
                autonomus_history.add_record("user","Make your next step.")

        prompt = self.prompts["autonomous_finish_prompt"].format(task="your own tasks")
        autonomus_history.add_record("user", prompt)
        payload.extend(autonomus_history.get_records())
        answer = self.providers_manager.generation_request(self.model, payload)
        self.state["autonomuse_notes"] = self._remove_thinking(answer).strip()
        self._save_state(self.config["context"]["state_path"])

        memory_symmary_prompt = self.prompts["memory_summary_prompt"]
        payload = autonomus_history.get_records() + [HistoryRecord("user", memory_symmary_prompt)]
        raw_memory_summary = self.providers_manager.generation_request(self.model, payload)
        memory_summary = raw_memory_summary[raw_memory_summary.find("{"):raw_memory_summary.rfind("}") + 1]
        memory_summary_list = json.loads(memory_summary)["important_facts"]
        print("\n" + str(memory_summary_list) + "\n")
        for fact in memory_summary_list:
            if self.memory:
                self.memory.add_memory(fact.strip())
            
    def _parse_toolcall(self, message: str) -> dict | None:
        if "toolcall" in message:
            toolcall = message[message.find("{\"toolcall"):message.rfind("}")+1]
            try:
                return json.loads(toolcall, strict=False)["toolcall"]
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON toolcall: {e}")
                print(f"Raw malformed json: {toolcall}")
                return None
        return None
    
    def _use_tool(self, toolcall: dict) -> str:
        tool_summary_prompt = self.prompts["tool_summary_prompt"]
        result = ""
        if toolcall["name"] in self.tool_table:
            result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
            if result["tool_result"]:
                if len(result["tool_result"]) > 2500:
                    payload = [HistoryRecord("user", tool_summary_prompt.format(toolcall["name"], result["tool_result"]))]
                    result["tool_result"] = self.providers_manager.generation_request(self.model, payload)
                    result["summarized"] = True
        else:
            result={"tool_name": toolcall["name"], "tool_arguments": toolcall["arguments"], "tool_result": None, "truncate": False, "error": "Error: Tool not found"}
        print("tool:" + str(result))
        return str(result)
    
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