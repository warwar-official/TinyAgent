import datetime
import json
import os

class ExecutionTraceManager:
    """
    Manages a concise trace of the last N execution steps across tasks.
    Used to provide Router and Formatter with a lightweight context
    instead of the full, heavy task history.
    """
    def __init__(self, max_steps: int = 20, filepath: str = "./data/execution_trace.json"):
        self.max_steps = max_steps
        self.filepath = filepath
        self.trace = {"tasks": []}
        self._current_task_title = None
        self._step_count = 0
        self._load_state()

    def _load_state(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "tasks" in data:
                        self.trace = data
                        self._step_count = sum(len(task.get("steps", [])) for task in self.trace["tasks"])
            except Exception as e:
                print(f"Failed to load execution trace from {self.filepath}: {e}")

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.trace, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save execution trace to {self.filepath}: {e}")

    def start_task(self, title: str):
        """Starts a new task block in the trace."""
        self._current_task_title = title
        # Don't add to trace until the first step is added.

    def add_step(self, action: str, args: dict, status: str, tool_name: str = None):
        """Adds a step to the current task block."""
        if not self._current_task_title:
            self._current_task_title = "Unknown Task"

        # Check if the last task block is the current one
        if not self.trace["tasks"] or self.trace["tasks"][-1]["title"] != self._current_task_title:
            self.trace["tasks"].append({
                "title": self._current_task_title,
                "steps": []
            })
            
        current_task_block = self.trace["tasks"][-1]
        
        # Format timestamp: HH:MM | Day Number Month
        now = datetime.datetime.now()
        timestamp = now.strftime("%H:%M | %a %-d %B") # e.g., 14:32 | Fri 27 March
        
        # Determine type
        step_type = "Tool" if action == "tool" else "Action"
        if action == "system":
            step_type = "System"
            
        # Clean/shorten args
        short_args = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 200:
                short_args[k] = v[:200] + "..."
            elif isinstance(v, (dict, list)):
                # Just show that it's a complex object instead of full JSON
                short_args[k] = f"<{type(v).__name__} object>"
            else:
                short_args[k] = v

        new_step = {
            "time": timestamp,
            "type": step_type,
            "name": tool_name if tool_name else action,
            "args": short_args,
            "status": status.capitalize() # Success / Failed / Pending
        }
        
        current_task_block["steps"].append(new_step)
        self._step_count += 1
        
        self._trim()
        self._save_state()

    def _trim(self):
        """Removes oldest steps if we exceed max_steps."""
        while self._step_count > self.max_steps:
            if not self.trace["tasks"]:
                break
                
            oldest_task = self.trace["tasks"][0]
            if oldest_task["steps"]:
                oldest_task["steps"].pop(0)
                self._step_count -= 1
            
            # If a task has no steps left, remove the task block entirely
            if not oldest_task["steps"]:
                self.trace["tasks"].pop(0)

    def get_trace(self) -> dict:
        """Returns the execution trace as a dict."""
        return self.trace

    def get_structured_trace(self) -> dict:
        """Returns the structured execution trace for PromptMCP."""
        return self.trace
