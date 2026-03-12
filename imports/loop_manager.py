from dataclasses import dataclass
from imports.history_manager import HistoryManager, HistoryRecord
from imports.providers_manager import ProvidersManager, Model
from imports.memory_rag import MemoryRAG
from imports.task_manager import TaskManager
from imports.image_manager import ImageManager
from imports.mcp.connector import MCPConnector
import json
import re
import os
import threading
import queue

DEBUG = os.getenv("DEBUG", False)


@dataclass
class AgentMessage:
    """Message passed from the frontend to LoopManager."""
    text: str
    image_hash: str | None = None

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
SUMMARIZE_LEN = 15
MIN_SUMURIZE_LEN = SUMMARIZE_LEN / 2

class LoopManager:
    """Core manager for user and autonomous instruction execution."""
    
    def __init__(self, config: dict, image_manager: ImageManager) -> None:
        self.config = config
        # Base components
        self.providers_manager = ProvidersManager(self.config["providers"])
        self.model = Model(**self.config["agent"]["model"])
        self.summary_model = Model(**self.config["agent"]["summary_model"])
        self.conversation_history = HistoryManager(self.config["context"]["conversation_history_path"])
        # Task components
        self.task_history = HistoryManager(self.config["context"]["task_history_path"])
        self.task_manager = TaskManager(self.config["context"]["tasks_path"])
        self._load_callbacks()
        # Memory manager
        if self.config["context"]["memory"]["active"]:
            self.memory = MemoryRAG(self.config)
            # Memory worker thread
            self.memory_queue = queue.Queue()
            self.memory_worker_thread = threading.Thread(target=self._memory_worker, daemon=True)
            self.memory_worker_thread.start()
        else:
            self.memory = None
        # Prompts and state 
        self.retrived_memory = "None"
        # Prompts and state 
        self.retrived_memory = "None"
        
        # Image manager (shared with main.py)
        self.image_manager = image_manager
        
        # MCP connector using dynamic configuration
        mcp_config_path = self.config["context"].get("mcp_config_path", "./tools/mcp_config.json")
        try:
            with open(mcp_config_path, "r", encoding="utf-8") as f:
                mcp_config_data = json.load(f)
        except Exception as e:
            print(f"Failed to load MCP config {mcp_config_path}: {e}")
            mcp_config_data = {}
            

        # Optional: Inject shared QdrantClient if MemoryRAG is active to avoid db locking
        if self.config["context"]["memory"]["active"] and self.memory:
            for server_cfg in mcp_config_data.get("servers", []):
                if server_cfg.get("name") == "retrieval":
                    # We pass the already instantiated client and model instead of paths
                    # This requires modifying tools/retrieval_mcp.py to accept them
                    server_cfg["init_params"] = {
                        "client": self.memory.client,
                        "embedding_model": self.memory.embedding_model
                    }

        self.mcp_connector = MCPConnector(config_data=mcp_config_data) # type: ignore
        
        # Load state (after connector, since _init_state fallback uses it)
        self.state = self._load_state(self.config["context"]["state_path"])

    def init_agent(self):
        if self.state.state == "none":
            self.state.state = "task"
            self.state.identity = self.mcp_connector.generate_prompt("default_identity_prompt", {})
            self.state.current_task = "identity_setup"
            self.task_manager.restart_task("identity_setup")
            return self._task_loop("")
        else:
            return "Agent already initialized."

    def router(self, message: AgentMessage) -> str:
        # Vision validation
        if message.image_hash and not self.model.vision_enabled:
            return "This model does not support image inputs."
        if self.state.state == "ready":
            self._retrive_memory(message.text)
            answer = self._request_loop(message)
        elif self.state.state == "task":
            answer = self._task_loop(message.text)
        else:
            answer = "Agent not initialized. Start commant '/init'."
        return answer
    
    def own_task(self):
        self.state.state = "task"
        self.state.current_task = "own_task"
        self.task_manager.restart_task("own_task")
        return self._task_loop("")
    
    def identity_rethink(self) -> str:
        """Trigger an identity rethinking process pulling recent history."""
        self.state.state = "task"
        self.state.current_task = "identity_rethink"
        self.task_manager.restart_task("identity_rethink")
        conversation = self.conversation_history.get_records(8)
        for record in conversation:
            self.task_history.add_record(record.role, record.message)
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
                self.task_history.set_old_records_mark()
                return True
            return False
        # Preparing input, to orevent instructions injection
        input = "Interpret this message in context of your current task: " + input
        try:
            # Preparing instruction
            if self.task_manager.get_task_status(self.state.current_task) == "active":
                subtask = self.task_manager.get_current_subtask(self.state.current_task)
                instruction = subtask.instruction
                instruction += self.mcp_connector.generate_prompt("task_stopword_prompt", {"instruction": subtask.instruction, "stop_word": subtask.stop_word})
                input = instruction
            else:
                subtask = self.task_manager.get_current_subtask(self.state.current_task)
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
                    input = "Continue."
            return "Loop exceed limit of steps per task. But task was not completed."

    def _request_loop(self, input: AgentMessage | str, task: bool = False, tool_available: bool = True) -> str:
        # Normalize input
        if isinstance(input, str):
            input = AgentMessage(text=input)
        def _add_record(type: str, message: str, image_hash: str | None = None) -> None:
            if task:
                self.task_history.add_record(type, self._remove_thinking(message), image_hash=image_hash)
            else:
                self.conversation_history.add_record(type, self._remove_thinking(message), image_hash=image_hash)
        self._retrive_memory(input.text)
        _add_record("user", input.text, image_hash=input.image_hash)
        if task:
            payload = self._make_payload(tool=tool_available, history=True, task=True)
        else:
            payload = self._make_payload()
        answer = self.providers_manager.generation_request(
            self.model, payload,
            encode_images=True,
            image_resolver=self.image_manager.get_image_base64,
        )
        _add_record("model", answer)
        toolcall = self._parse_toolcall(answer)
        while toolcall:
            tool_result = self._execute_tool(toolcall)
            _add_record("tool", self.mcp_connector.generate_prompt("tool_result_template", {"name": toolcall["name"], "result": tool_result}))
            if task:
                payload = self._make_payload(tool=tool_available, history=True, task=True)
            else:
                payload = self._make_payload()
            answer = self.providers_manager.generation_request(
                self.model, payload,
                encode_images=True,
                image_resolver=self.image_manager.get_image_base64,
            )
            _add_record("model", answer)
            toolcall = self._parse_toolcall(answer)
            if task:
                if len(self.task_history.get_records()) > SUMMARIZE_LEN:
                    self._summarise(task=True)
            else:
                if len(self.conversation_history.get_records()) > SUMMARIZE_LEN:
                    self._summarise()
        return self._remove_thinking(answer.strip())

    def _summarise(self, task: bool = False, memory: bool = True) -> None:
        # Creating summary
        if task:
            conversation_summary_prompt = self.mcp_connector.generate_prompt("task_summary_prompt", {})
            prev_records = self.task_history.get_records()
            prev_records.insert(0, HistoryRecord("model", "Current task summary: " + self.state.task_summary))
            source = "task"
        else:
            conversation_summary_prompt = self.mcp_connector.generate_prompt("conversation_summary_prompt", {})
            prev_records = self.conversation_history.get_records()
            if len(prev_records) < MIN_SUMURIZE_LEN:
                if DEBUG:
                    print("Not enough records to summarise.")
                return
            prev_records.insert(0, HistoryRecord("model", "Current conversation summary: " + self.state.conversation_summary))
            source = "conversation"
        payload = prev_records + [HistoryRecord("user", conversation_summary_prompt)]
        answer = self.providers_manager.generation_request(self.summary_model, payload, encode_images=False)
        if task:
            self.state.task_summary = self._remove_thinking(answer)
        else:
            self.state.conversation_summary = self._remove_thinking(answer)
        self._save_state(self.config["context"]["state_path"])
        # Creating memories
        if memory:
            if self.config["context"]["memory"]["active"]:
                self.memory_queue.put((list(prev_records), source))
        if task:
            self.task_history.set_old_records_mark(5)
        else:
            self.conversation_history.set_old_records_mark(5)

    def _retrive_memory(self, user_input: str) -> None:
        if self.memory:
            self.retrived_memory = self.memory.search(user_input)
            if self.retrived_memory == []:
                self.retrived_memory = "None"

    def _memory_worker(self) -> None:
        while True:
            try:
                prev_records, source = self.memory_queue.get()
                memory_summary_prompt = self.mcp_connector.generate_prompt("memory_summary_prompt", {})
                payload = prev_records + [HistoryRecord("user", memory_summary_prompt)]
                raw_memory_summary = self.providers_manager.generation_request(self.summary_model, payload, encode_images=False)
                memory_summary = raw_memory_summary[raw_memory_summary.find("{"):raw_memory_summary.rfind("}") + 1]
                memory_summary_list = json.loads(memory_summary).get("important_facts", [])
                if DEBUG:
                    print("\n" + str(memory_summary_list) + "\n")
                for fact in memory_summary_list:
                    if self.memory:
                        self.memory.add_memory(fact.strip(), source, "summary")
            except Exception as e:
                print(f"Failed extracting background memories: {e}")

    def _make_payload(self, tool: bool = True, history: bool = True, task: bool = False) -> list[HistoryRecord]:
        # Tool description
        if tool:
            tool_description = self._format_tool_descriptions(self.mcp_connector.get_tools())
        else:
            tool_description = ""
        # Task info block
        if task:
            subtask = self.task_manager.get_current_subtask(self.state.current_task)
            task_info = (
                "[TASK]\n"
                f"You are performing task now. Follow the instructions.\n"
                f"Task: \"{subtask.instruction}\"\n"
                f"When you done with this task, say \"{subtask.stop_word}\" to go to the next step. This phrase system valuable. so don't use it in another meaning except finishing step."
                "[END_TASK]"
            )
        else:
            task_info = ""
        # System prompt via MCP
        ability_prompt = self.mcp_connector.get_ability_prompt()
        system_prompt = self.mcp_connector.generate_prompt("system_prompt", {
            "identity": self.state.identity,
            "tool_description": tool_description,
            "ability_prompt": ability_prompt,
            "retrieved_memory": self.retrived_memory if self.retrived_memory else "None",
            "autonomous_notes": self.state.autonomouse_notes,
            "task_info": task_info,
        })
        system_record = [HistoryRecord("system", system_prompt)]
        # Conversation summary
        summary = []
        if task:
            if self.state.task_summary != "":
                summary = [HistoryRecord("model", self.state.conversation_summary)] + [HistoryRecord("model", self.state.task_summary)]
        else:
            if self.state.conversation_summary != "":
                summary = [HistoryRecord("model", self.state.conversation_summary)]
        # History 
        if history:
            if task:
                payload = system_record + summary + self.task_history.get_records()
            else:
                payload = system_record + summary + self.conversation_history.get_records()
        else:
            payload = system_record + summary
        return payload

    @staticmethod
    def _load_prompts(path: str) -> dict:
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
        default_identity = self.mcp_connector.generate_prompt("default_identity_prompt", {})
        return LoopState(
            state="none",
            identity=default_identity,
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
    
    def _execute_tool(self, toolcall: dict) -> str:
        """Execute a tool via MCP and optionally summarize long results."""
        try:
            result = self.mcp_connector.execute_tool(toolcall["name"], toolcall["arguments"])
            if result.get("tool_result"):
                tool_result_str = str(result["tool_result"])
                if len(tool_result_str) > 5000:
                    summary_prompt = self.mcp_connector.generate_prompt("tool_summary_prompt", {"tool_name": toolcall["name"], "result": tool_result_str})
                    payload = [HistoryRecord("user", summary_prompt)]
                    result["tool_result"] = self.providers_manager.generation_request(self.summary_model, payload, encode_images=False)
                    result["summarized"] = True
        except Exception as e:
            result = {"tool_name": toolcall["name"], "tool_arguments": toolcall["arguments"],
                      "tool_result": None, "truncate": False, "error": str(e)}
        print("tool:" + str(result))
        return str(result)

    @staticmethod
    def _format_tool_descriptions(tools: list[dict]) -> str:
        """Convert a list of tool schemas into the text format the model expects."""
        prompt = ""
        for tool in tools:
            prompt += f"\n{tool['name']}: {tool.get('description', '')}\nParameters: {tool.get('parameters', {})}\n"
        return prompt
    
    def _remove_thinking(self, message: str) -> str:
        return re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL)