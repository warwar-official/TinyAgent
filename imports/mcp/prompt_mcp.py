from imports.mcp.base import MCPServer
from datetime import datetime
import json

class PromptMCP(MCPServer):
    """MCP server that generates all system prompts."""

    def __init__(self, app_config: dict = None) -> None:
        prompts_path = app_config["context"]["prompts_path"]
        self._prompts = self._load_prompts(prompts_path)

    @staticmethod
    def _load_prompts(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"PromptMCP: Failed to read prompts from {path}: {e}")
            return {}

    def _rpc_prompt_generate(self, params: dict) -> str:
        name: str = params.get("name", "")
        args: dict = params.get("arguments", {})

        generators = {
            "system_prompt": self._build_system_prompt,
            "conversation_summary_prompt": self._build_simple,
            "task_summary_prompt": self._build_simple,
            "memory_summary_prompt": self._build_simple,
            "tool_summary_prompt": self._build_formatted,
            "tool_result_template": self._build_formatted,
            "task_stopword_prompt": self._build_formatted,
            "default_identity_prompt": self._build_simple,
            # Formatting methods
            "format_identity": self.format_identity,
            "format_execution_trace": self.format_execution_trace,
            "format_system_state": self.format_system_state,
            "format_memory": self.format_memory,
            "format_history": self.format_history,
            "format_user_input": self.format_user_input,
            "format_payload": self.format_payload,
        }

        builder = generators.get(name)
        if builder is None:
            if name in self._prompts:
                return self._prompts[name]
            raise ValueError(f"Unknown prompt: {name}")

        if builder == self._build_simple:
            return self._prompts.get(name, "")
        elif builder == self._build_formatted:
            template = self._prompts.get(name, "")
            return template.format(**args)
        else:
            return builder(args)

    def format_identity(self, args: dict) -> str:
        identity = args.get("identity", "")
        if not identity:
            return ""
        return f"### Identity\n{identity}\n"

    def format_execution_trace(self, args: dict) -> str:
        trace_data = args.get("trace", {})
        if not trace_data or not trace_data.get("tasks"):
            return ""
            
        lines = ["### Execution Trace\n"]
        for task in trace_data["tasks"]:
            lines.append(f"#### Task: {task['title']}\n")
            for i, step in enumerate(task["steps"], 1):
                time = step.get("time", "")
                stype = step.get("type", "Tool")
                name = step.get("name", "")
                status = step.get("status", "Pending")
                args_dict = step.get("args", {})
                
                lines.append(f"{i}. [{time}] {stype}: {name}")
                if args_dict:
                    lines.append(f"   → Args: {json.dumps(args_dict, ensure_ascii=False)}")
                lines.append(f"   → Status: {status}\n")
        return "\n".join(lines).strip() + "\n"

    def format_system_state(self, args: dict) -> str:
        current_time = args.get("current_time", "")
        if not current_time:
            # Fallback to local time if not provided
            current_time = datetime.now().strftime("%H:%M | %a %-d %B")
        return f"### System State\n**Current Time:** {current_time}\n"

    def format_memory(self, args: dict) -> str:
        memories = args.get("memories", [])
        if not memories:
            return ""
        
        lines = ["### Memory / Retrieved Data"]
        for i, mem in enumerate(memories, 1):
            if isinstance(mem, dict):
                content = mem.get("content", str(mem))
                lines.append(f"{i}. **Memory:** {content}")
            else:
                lines.append(f"{i}. **Memory:** {mem}")
        return "\n".join(lines) + "\n"

    def format_history(self, args: dict) -> str:
        history = args.get("history", [])
        if not history:
            return ""
            
        lines = ["### Conversation History"]
        for i, entry in enumerate(history, 1):
            if hasattr(entry, "to_dict"):
                entry = entry.to_dict()
            
            # If it's a dict
            if isinstance(entry, dict):
                role = entry.get("role", "user").capitalize()
                message = entry.get("message", "")
                time = entry.get("create_time", "")
                
                if role.lower() == "user" and time:
                    try:
                        # Handle potential datetime object or string
                        if isinstance(time, str):
                            dt = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
                        else:
                            dt = time
                        time_str = dt.strftime("%H:%M | %a %-d %B")
                        lines.append(f"{i}. **{role}:** [{time_str}] {message}")
                    except:
                        lines.append(f"{i}. **{role}:** {message}")
                else:
                    lines.append(f"{i}. **{role}:** {message}")
            else:
                lines.append(f"{i}. **Entry:** {str(entry)}")
        
        return "\n".join(lines) + "\n"

    def format_user_input(self, args: dict) -> str:
        user_input = args.get("user_input", "")
        return f"**User Input:** {user_input}\n"

    def format_payload(self, args: dict) -> str:
        """
        Standardizes the payload structure based on the new hierarchy:
        1. Identity
        2. Execution Trace
        3. System State
        4. Memory / Retrieved Data
        5. History
        6. User Input (LAST)
        """
        parts = []
        
        # 1. Identity
        if "identity" in args:
            parts.append(self.format_identity({"identity": args["identity"]}))
            
        # 2. Execution Trace
        if "trace" in args:
            parts.append(self.format_execution_trace({"trace": args["trace"]}))
            
        # 3. System State
        system_state = self.format_system_state({"current_time": args.get("current_time")})
        parts.append(system_state)
        
        # 4. Memory / Retrieved Data
        if "memories" in args:
            parts.append(self.format_memory({"memories": args["memories"]}))
            
        # 5. History
        if "history" in args:
            parts.append(self.format_history({"history": args["history"]}))
            
        # 6. User Input
        if "user_input" in args:
            parts.append(self.format_user_input({"user_input": args["user_input"]}))
            
        return "\n".join([p for p in parts if p.strip()])

    def _build_system_prompt(self, args: dict) -> str:
        identity = args.get("identity", "")
        tool_description = args.get("tool_description", "")
        ability_prompt = args.get("ability_prompt", "")
        retrieved_memory = args.get("retrieved_memory", "None")
        autonomous_notes = args.get("autonomous_notes", "")
        task_info = args.get("task_info", "")

        tools_prompt = self._prompts.get("tools_prompt", "")
        security_prompt = self._prompts.get("securety_prompt", "")

        system_prompt = (
            "[SYSTEM]\n"
            "# IDENTITY SECTION\n"
            f"{identity}\n"
            "# TECHNICAL SECTION\n"
            f"{ability_prompt}\n"
            f"{tools_prompt}\n"
            f"{tool_description}\n"
            "# RUNTIME STATE\n"
            f"Current date and time: {datetime.now().strftime('%H:%M | %a %-d %B')}\n"
            f"Retrived memories:\n{retrieved_memory}\n"
            f"Notes from the autonomus loop:\n{autonomous_notes}\n"
            f"{security_prompt}\n"
            "[END_SYSTEM]\n"
        )

        if task_info:
            system_prompt += task_info

        return system_prompt

    def _build_simple(self, args: dict) -> str:
        return ""

    def _build_formatted(self, args: dict) -> str:
        return ""
