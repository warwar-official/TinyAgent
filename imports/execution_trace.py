import datetime

class ExecutionTraceManager:
    """
    Manages a concise trace of the last N execution steps across tasks.
    Used to provide Router and Formatter with a lightweight context
    instead of the full, heavy task history.
    """
    def __init__(self, max_steps: int = 20):
        self.max_steps = max_steps
        self.trace = {"tasks": []}
        self._current_task_title = None
        self._step_count = 0

    def start_task(self, title: str):
        """Starts a new task block in the trace."""
        self._current_task_title = title
        # Don't add to trace until the first step is added.

    def add_step(self, action: str, args: dict, status: str):
        """Adds a step to the current task block."""
        if not self._current_task_title:
            self._current_task_title = "Unknown Task"

        # Check if the last task block is the current one
        if not self.trace["tasks"] or self.trace["tasks"][-1]["title"] != self._current_task_title:
            self.trace["tasks"].append({
                "title": f"Task: {self._current_task_title}",
                "steps": []
            })
            
        current_task_block = self.trace["tasks"][-1]
        
        # Format timestamp "HH:MM DayOfWeek"
        now = datetime.datetime.now()
        timestamp = now.strftime("%H:%M %a")
        
        step_id = f"step_{len(current_task_block['steps']) + 1:02d}"
        
        # Clean/shorten args if needed (e.g., truncate very long strings)
        short_args = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 100:
                short_args[k] = v[:100] + "..."
            else:
                short_args[k] = v

        new_step = {
            "id": step_id,
            "action": action,
            "args": short_args,
            "status": status,
            "timestamp": timestamp
        }
        
        current_task_block["steps"].append(new_step)
        self._step_count += 1
        
        self._trim()

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
