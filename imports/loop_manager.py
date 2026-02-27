from dataclasses import dataclass
from imports import task_manager
from imports.history_manager import HistoryManager, HistoryRecord
from imports.providers_manager import ProvidersManager, Model
from imports.memory_manager import MemoryManager
from imports.task_manager import TaskManager
from datetime import datetime, timedelta
import json
import importlib
import re

@dataclass
class LoopState:
    state: str
    identity: str
    conversation_summary: str
    task_summary: str
    autonomouse_notes: str
    current_task: str

    def to_json(self) -> dict:
        return {
            "state": self.state,
            "identity": self.identity,
            "conversation_summary": self.conversation_summary,
            "task_summary": self.task_summary,
            "autonomouse_notes": self.autonomouse_notes,
            "current_task": self.current_task
        }

    @staticmethod
    def from_json(json_data: dict) -> "LoopState":
        return LoopState(
            state=json_data["state"],
            identity=json_data["identity"],
            conversation_summary=json_data["conversation_summary"],
            task_summary=json_data["task_summary"],
            autonomouse_notes=json_data["autonomouse_notes"],
            current_task=json_data["current_task"]
        )

STEP_PER_TASK_LIMIT = 15
SUMMARIZE_LEN = 20
MIN_SUMURIZE_LEN = 10

class LoopManager:
    def __init__(self, config: dict) -> None:
        # Save config, we need it farther
        self.config = config
        # Base components
        self.providers_manager = ProvidersManager(self.config["providers"])
        self.model = Model(**self.config["agent"]["model"])
        self.conversation_history = HistoryManager(self.config["context"]["conversation_history_path"])
        # Task components
        self.task_history = HistoryManager(self.config["context"]["task_history_path"])
        self.task_manager = TaskManager(self.config["context"]["tasks_path"])
        self._load_callbacks()
        # Memory manager
        if self.config["context"]["memory"]["active"]:
            self.memory = MemoryManager(self.config)
        else:
            self.memory = None
        # Prompts and state 
        self.retrived_memory = "None"
        self.prompts = self._load_prompts(self.config["context"]["prompts_path"])
        self.state = self._load_state(self.config["context"]["state_path"])
        # Tools
        self.tool_table = self._load_tools(self.config)
        self.tool_description = self._make_tool_description(self.config)

    def init_agent(self):
        if self.state.state == "none":
            self.state.state = "task"
            self.state.identity = self.prompts["default_identity_prompt"]
            self.state.current_task = "identity_setup"
            self.task_manager.activate_task("identity_setup")
            return self._task_loop("")
        else:
            return "Agent already initialized."

    def router(self, user_input: str) -> str:
        if self.state.state == "ready":
            self._retrive_memory(user_input)
            answer = self._request_loop(user_input)
        elif self.state.state == "task":
            answer =  self._task_loop(user_input)
        else:
            answer = "Agent not initialized. Start commant '/init'."
        return answer
    
    def autonomous_loop(self):
        self.state.state = "task"
        self.state.current_task = "own_task"
        self.task_manager.activate_task("own_task")
        return self._task_loop("")

    def _task_loop(self, input: str) -> str:
        def _check_and_clear(answer: str) -> bool:
            # Post-step callback
            subtask = self.task_manager.get_current_subtask(self.state.current_task) 
            if not subtask.callback == "none":
                if subtask.callback in self.callbacks:
                    self.callbacks[subtask.callback](answer)
                else:
                    raise Exception(f"Callback {subtask.callback} not found.")
            print("NEXT STEP")
            self.task_manager.next_step(self.state.current_task)
            # Task completion check    
            if self.task_manager.is_task_completed(self.state.current_task):
                self.state.task_summary = ""
                self.state.state = "ready"
                self.state.current_task = "none"
                self._save_state(self.config["context"]["state_path"])
                return True
            return False
        # Preparing input, to orevent instructions injection
        input = "Interpret this message in context of your current task: " + input
        try:
            # Preparing instruction
            subtask = self.task_manager.get_current_subtask(self.state.current_task)
            if self.task_manager.get_task_status(self.state.current_task) == "active":
                instruction = subtask.instruction
                instruction += f"\nWhen you done with this task, say \"{subtask.stop_word}\" to go to the next step. This phrase system valuable. so don't use it in another meaning except finishing step."
                input = instruction
        except Exception as e:
            return str(e)
        if subtask.interactive:
            # Interactive loop
            answer = self._request_loop(input, task=True, tool_available=subtask.tool_available)
            if subtask.stop_word in answer:
                answer = answer.replace(subtask.stop_word, "")
                if _check_and_clear(answer):
                    return answer
                self._summarise(task=True, memory=False)
                return self._task_loop("")
            return answer
        else:
            # Non-interactive loop
            for i in range(STEP_PER_TASK_LIMIT):
                answer = self._request_loop(input, task=True, tool_available=subtask.tool_available)
                if subtask.stop_word in answer:
                    answer = answer.replace(subtask.stop_word, "")
                    
                    if _check_and_clear(answer):
                        return "Task completed."
                    else:
                        self._summarise(task=True, memory=False)
                        subtask = self.task_manager.get_current_subtask(self.state.current_task)
                        if subtask.instruction:
                            input = subtask.instruction
                        else:
                            raise Exception("Unexpected behavior betwen steps. Step without instruction.")
                else:
                    input = "Make your next step."
            return "Loop exceed limit of steps per task. But task was not completed."

    def _request_loop(self, input: str, task: bool = False, tool_available: bool = True) -> str:
        def _add_record(type: str, message: str) -> None:
            if task:
                self.task_history.add_record(type,message)
            else:
                self.conversation_history.add_record(type,message)
        self._retrive_memory(input)
        _add_record("user",input)
        if task:
            payload = self._make_payload(tool=tool_available, history=True, task=True)
        else:
            payload = self._make_payload()
        answer = self.providers_manager.generation_request(self.model, payload)
        _add_record("model",answer)
        toolcall = self._parse_toolcall(answer)
        while toolcall:
            tool_result = self._use_tool(toolcall)
            _add_record("tool",self.prompts["tool_result_template"].format(name=toolcall["name"], result=tool_result))
            if task:
                payload = self._make_payload(tool=tool_available, history=True, task=True)
            else:
                payload = self._make_payload()
            answer = self.providers_manager.generation_request(self.model, payload)
            _add_record("model",answer)
            toolcall = self._parse_toolcall(answer)
            if task:
                if len(self.task_history.get_records()) > SUMMARIZE_LEN:
                    self._summarise(task=True)
            else:
                if len(self.conversation_history.get_records()) > SUMMARIZE_LEN:
                    self._summarise()
        return self._remove_thinking(answer.strip())

    def _summarise(self, task: bool = False, memory: bool = True) -> None:
        if task:
            conversation_summary_prompt = self.prompts["task_summary_prompt"]
            prev_records = self.task_history.get_records()
            prev_records.insert(0, HistoryRecord("model", "Current task summary: " + self.state.task_summary))
        else:
            conversation_summary_prompt = self.prompts["conversation_summary_prompt"]
            prev_records = self.conversation_history.get_records()
            if len(prev_records) < MIN_SUMURIZE_LEN:
                print("Not enough records to summarise.")
                return
            prev_records.insert(0, HistoryRecord("model", "Current conversation summary: " + self.state.conversation_summary))
        payload = prev_records + [HistoryRecord("user", conversation_summary_prompt)]
        answer = self.providers_manager.generation_request(self.model, payload)
        if task:
            self.state.task_summary = self._remove_thinking(answer)
        else:
            self.state.conversation_summary = self._remove_thinking(answer)
        self._save_state(self.config["context"]["state_path"])

        if memory:
            if self.config["context"]["memory"]["active"]:
                memory_symmary_prompt = self.prompts["memory_summary_prompt"]
                payload = self.conversation_history.get_records() + [HistoryRecord("user", memory_symmary_prompt)]
                raw_memory_summary = self.providers_manager.generation_request(self.model, payload)
                memory_summary = raw_memory_summary[raw_memory_summary.find("{"):raw_memory_summary.rfind("}") + 1]
                memory_summary_list = json.loads(memory_summary)["important_facts"]
                print("\n" + str(memory_summary_list) + "\n")
                for fact in memory_summary_list:
                    if self.memory:
                        self.memory.add_memory(fact.strip())
        if task:
            self.task_history.set_old_records_mark(5)
        else:
            self.conversation_history.set_old_records_mark(5)

    def _retrive_memory(self, user_input: str) -> None:
        if self.memory:
            self.retrived_memory = self.memory.search(user_input)
            if self.retrived_memory == []:
                self.retrived_memory = "None"

    def _make_payload(self, tool: bool = True, history: bool = True, task: bool = False) -> list[HistoryRecord]:
        # Tool description
        if tool:
            tool_description = self.tool_description
        else:
            tool_description = ""
        # Ability description 
        ability_description = self.prompts["ability_prompt"]
        # Last message time 
        last_user_message = self.conversation_history.get_last_record("user")
        if last_user_message:
            last_message_time = last_user_message.create_time
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
        # System prompt 
        system_prompt = (
            "[SYSTEM]\n\n"
            "# IDENTITY SECTION\n\n"
            f"{self.state.identity}\n\n"
            "# TECHNICAL SECTION\n\n"
            f"{ability_description}\n\n"
            f"{self.prompts['tools_prompt']}\n"
            f"{tool_description}\n\n"
            "# RUNTIME STATE\n\n"
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Last message from user: {last_message_time_str} ago\n"
            f"Retrived memories:\n{self.retrived_memory}\n"
            f"Notes from the autonomus loop:\n{self.state.autonomouse_notes}\n"
            "[END_SYSTEM]\n"
        )

        if task:
            subtask = self.task_manager.get_current_subtask(self.state.current_task)
            task_instruct = (
                "[TASK]\n"
                f"You are performing task now. Follow the instructions.\n"
                f"Task: \"{subtask.instruction}\"\n"
                f"When you done with this task, say \"{subtask.stop_word}\" to go to the next step. This phrase system valuable. so don't use it in another meaning except finishing step."
                "[END_TASK]"
            )
        else:
            task_instruct = ""
        system_prompt += task_instruct
        system_record = [HistoryRecord("system", system_prompt)]
        # Conversation summary
        if task:
            if self.state.task_summary != "":
                system_record.append(HistoryRecord("model", self.state.task_summary))
        else:
            if self.state.conversation_summary != "":
                system_record.append(HistoryRecord("model", self.state.conversation_summary))
        # History 
        if history:
            if task:
                payload = system_record + self.task_history.get_records()
            else:
                payload = system_record + self.conversation_history.get_records()
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

    def _load_state(self, path: str) -> LoopState:
        try:
            with open(path, "r") as f:
                return LoopState.from_json(json.load(f))
        except IOError as e:
            print(f"Unable to read state! Error: {e}")
        except json.JSONDecodeError as e:
            print(f"Unable to decode state! Error: {e}")
        return self._init_state()
    
    def _save_state(self, path: str) -> None:
        try:
            with open(path, "w") as f:
                json.dump(self.state.to_json(), f, ensure_ascii=False, indent=4)
        except IOError as e:
            print(f"Unable to write state! Error: {e}")
    
    def _init_state(self) -> LoopState:
        return LoopState(
            state="none",
            identity=self.prompts["default_identity_prompt"],
            conversation_summary="",
            task_summary="",
            autonomouse_notes="",
            current_task="none"
        )
    
    def _load_callbacks(self) -> None:
        self.callbacks = {
            "identity_setup": self._identity_setup,
            "autonomous_completion": self._autonomous_completion
        }
    
    def _identity_setup(self, answer: str) -> None:
        self.state.identity = answer
        self._save_state(self.config["context"]["state_path"])
    
    def _autonomous_completion(self, answer: str) -> None:
        self.state.autonomouse_notes = answer
        self._save_state(self.config["context"]["state_path"])
        with open("autonomous_notes.ndjson", "a") as f:
            json.dump({"note" : self.state.autonomouse_notes}, f, ensure_ascii=False)
            f.write("\n")
            
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
            try:
                result = self.tool_table[toolcall["name"]](**toolcall["arguments"])
                if result["tool_result"]:
                    if len(result["tool_result"]) > 2500:
                        payload = [HistoryRecord("user", tool_summary_prompt.format(toolcall["name"], result["tool_result"]))]
                        result["tool_result"] = self.providers_manager.generation_request(self.model, payload)
                        result["summarized"] = True
            except Exception as e:
                result={"tool_name": toolcall["name"], "tool_arguments": toolcall["arguments"], "tool_result": None, "truncate": False, "error": str(e)}
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