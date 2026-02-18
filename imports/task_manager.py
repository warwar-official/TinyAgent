from dataclasses import dataclass

@dataclass
class Task:
    name: str
    desctiption: str
    priority: str
    status: str
    
class TaskManager:
    def __init__(self):
        self.tasks: list[Task] = []

    def add_task(self, name: str, description: str, priority: str) -> None:
        self.tasks.append(Task(name, description, priority, "active"))
    
    def finish_task(self, task_name: str) -> None:
        for task in self.tasks:
            if task.name == task_name:
                task.status = "finished"
                break
    
    def get_task(self) -> Task | None:
        priority_levels = ["high", "medium", "low"]
        for priority in priority_levels:
            task = [task for task in self.tasks if task.priority == priority and task.status == "active"]
            if task:
                return task[0]
        return None