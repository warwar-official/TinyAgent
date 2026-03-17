from dataclasses import dataclass, field
from datetime import datetime
from hashlib import md5
import os
import json

DEBUG = os.getenv("DEBUG", "False")

@dataclass
class HistoryRecord:
    hash: str
    create_time: datetime
    role: str
    message: str
    image_hashes: list[str]
    def __init__(self, role: str, message: str, create_time: datetime | None = None,
                 hash: str = "", image_hashes: list[str] | None = None) -> None:
        self.role = role
        self.message = message
        self.image_hashes = image_hashes or []
        if create_time:
            self.create_time = create_time
        else:
            self.create_time = datetime.now()
        if hash:
            self.hash = hash
        else:
            self.hash = md5((self.create_time.strftime("%S") + role + message).encode()).hexdigest()
    
    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "role": self.role,
            "message": self.message,
            "image_hashes": self.image_hashes
        }

class HistoryManager:
    def __init__(self, history_path: str = "") -> None:
        self.conversational_history: list[HistoryRecord] = []
        self.task_history: list[HistoryRecord] = []
        self.file_path: str | None = None
        
        if history_path:
            self.file_path = history_path
            self.load_history(history_path)
        else:
            print("Save path was not provided. Loaded in anonymous mode. No history will be saved.")

    def add_dialog_record(self, role: str, message: str, image_hashes: list[str] | None = None) -> None:
        """Adds a record to the persistent conversational history."""
        new_record = HistoryRecord(role, message.strip(), image_hashes=image_hashes or [])
        if DEBUG:
            print(f"Adding dialog record: {new_record}")
        self.conversational_history.append(new_record)
        self.save_history()

    def add_task_record(self, role: str, message: str, image_hashes: list[str] | None = None) -> None:
        """Adds a record to the short-lived task history."""
        new_record = HistoryRecord(role, message.strip(), image_hashes=image_hashes or [])
        if DEBUG:
            print(f"Adding task record: {new_record}")
        self.task_history.append(new_record)

    def get_dialog_records(self, count: int = 0) -> list[HistoryRecord]:
        """Returns the conversation history."""
        if count == 0:
            return self.conversational_history
        return self.conversational_history[-count:]

    def get_task_records(self, count: int = 0) -> list[HistoryRecord]:
        """Returns the current task history."""
        if count == 0:
            return self.task_history
        return self.task_history[-count:]

    def clear_task_history(self) -> None:
        """Wipes the task history after a task completes."""
        self.task_history = []
        if DEBUG:
            print("Task history cleared.")

    def save_history(self) -> None:
        """Saves only the conversational history."""
        if self.file_path:
            try:
                records_list = []
                for record in self.conversational_history:
                    records_list.append(record.to_dict())
                history_json = {
                    "records": records_list
                }
                with open(self.file_path, "w") as f:
                    json.dump(history_json, f, indent=4, ensure_ascii=False)
            except IOError as e:
                print(f"Failed to save history. Error: {e}")

    def compress_dialog_history(self, summary_text: str, keep_recent: int = 5) -> None:
        """Replaces old history with a summary node, keeping the most recent N messages."""
        if len(self.conversational_history) <= keep_recent:
            return
            
        recent = self.conversational_history[-keep_recent:]
        summary_record = HistoryRecord(role="model", message=f"Conversation Summary:\n{summary_text}")
        
        self.conversational_history = [summary_record] + recent
        self.save_history()

    def load_history(self, file_path: str) -> None:
        """Loads the conversational history. Supports both old (image_hash) and new (image_hashes) formats."""
        if file_path:
            try:
                with open(file_path, "r") as f:
                    history_json = json.load(f)
                    records_list = history_json.get("records", [])
                    for record in records_list:
                        # Backward compat: convert old image_hash to image_hashes
                        if "image_hashes" in record:
                            image_hashes = record["image_hashes"]
                        elif record.get("image_hash"):
                            image_hashes = [record["image_hash"]]
                        else:
                            image_hashes = []
                        
                        self.conversational_history.append(HistoryRecord(
                            record["role"],
                            record["message"],
                            datetime.strptime(record["create_time"], "%Y-%m-%d %H:%M:%S"),
                            record["hash"],
                            image_hashes=image_hashes
                        ))
            except IOError:
                print("History file not found or invalid format. Start anew.")
                self.conversational_history = []