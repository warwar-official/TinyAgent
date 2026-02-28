from dataclasses import dataclass
import json

@dataclass
class SubTask:
    name: str
    instruction: str
    stop_word: str
    interactive: bool
    tool_available: bool
    callback: str

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "instruction": self.instruction,
            "stop_word": self.stop_word,
            "interactive": self.interactive,
            "tool_available": self.tool_available,
            "callback": self.callback
        }
    
    @staticmethod
    def from_json(json_data: dict) -> "SubTask":
        return SubTask(
            name=json_data["name"],
            instruction=json_data["instruction"],
            stop_word=json_data["stop_word"],
            interactive=json_data["interactive"],
            tool_available=json_data["tool_available"],
            callback=json_data["callback"]
        )

@dataclass
class Task:
    name: str
    description: str
    status: str
    current_step: int
    subtasks: list[SubTask]

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "current_step": self.current_step,
            "subtasks": [subtask.to_json() for subtask in self.subtasks]
        }
    
    @staticmethod
    def from_json(json_data: dict) -> "Task":
        return Task(
            name=json_data["name"],
            description=json_data["description"],
            status=json_data["status"],
            current_step=json_data["current_step"],
            subtasks=[SubTask.from_json(subtask) for subtask in json_data["subtasks"]]
        )

class TaskManager:
    def __init__(self, path: str = "") -> None:
        self.path = path
        self._load_tasks()
    
    def add_task(self, task_json: dict) -> None:
        task = Task.from_json(task_json)
        self.tasks.append(task)
        self._save_tasks()
    
    def get_current_subtask(self, name: str) -> SubTask:
        for task in self.tasks:
            if task.name == name:
                if task.status in ("active", "processing"):
                    task.status = "processing"
                    self._save_tasks()
                    return task.subtasks[task.current_step]
        raise Exception("Task not found")
    
    def get_task_status(self, name: str) -> str:
        for task in self.tasks:
            if task.name == name:
                return task.status
        raise Exception("Task not found")
    
    def is_task_completed(self, name: str) -> bool:
        for task in self.tasks:
            if task.name == name:
                if task.status == "completed":
                    return True
        return False
    
    def next_step(self, name: str) -> None:
        for task in self.tasks:
            if task.name == name:
                if task.status == "processing":
                    task.current_step += 1
                    task.status = "active"
                    if task.current_step == len(task.subtasks):
                        task.status = "completed"
                    self._save_tasks()
                    return
        raise Exception("Task not found")
    
    def restart_task(self, name: str) -> None:
        for task in self.tasks:
            if task.name == name:
                task.status = "active"
                task.current_step = 0
                self._save_tasks()
                return
        raise Exception("Task not found")

    def terminate_task(self, name: str) -> None:
        for task in self.tasks:
            if task.name == name:
                if task.status == "active":
                    task.status = "terminated"
                    self._save_tasks()
                    return
        raise Exception("Task not found")

    def _load_tasks(self) -> None:
        if self.path:
            try:
                with open(self.path, "r") as f:
                    self.tasks = [Task.from_json(task) for task in json.load(f)]
            except Exception:
                self.tasks = []
                print("Tasks file not found. Start anew.")
        else:
            self.tasks = []
    
    def _save_tasks(self) -> None:
        if self.path:
            with open(self.path, "w") as f:
                json.dump([task.to_json() for task in self.tasks], f, indent=4)