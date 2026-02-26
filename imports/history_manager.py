from dataclasses import dataclass
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
    def __init__(self, role: str, message: str, create_time: datetime = datetime.now(), hash: str = "") -> None:
        self.create_time = create_time
        self.role = role
        self.message = message
        if hash:
            self.hash = hash
        else:
            self.hash = md5((self.create_time.strftime("%S") + role + message).encode()).hexdigest()
    
    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "role": self.role,
            "message": self.message
        }

class HistoryManager:
    def __init__(self, history_path: str = "") -> None:
        self.history: list[HistoryRecord] = []
        self.old_records_mark = 0
        if history_path:
            self.file_path = history_path
            self.load_history(history_path)
        else:
            self.file_path = None
            print("Save path was not provided. Loaded in anonimous mode. No history will be saved.")

    def add_record(self, role: str, message: str) -> None:
        new_record = HistoryRecord(role, message.strip())
        if DEBUG:
            print(f"Adding record: {new_record}")
        self.history.append(new_record)
        self.save_history()
    
    def get_records(self, count: int = 0) -> list[HistoryRecord]:
        if count == 0:
            records_list = self.history[self.old_records_mark:]
            return records_list
        records_list = self.history[0 - count:]
        return records_list
    
    def get_last_record(self, role: str) -> HistoryRecord | None:
        result = None 
        for record in self.history[-10:]:
            if record.role == role:
                result = record
        return result
    
    def set_old_records_mark(self, offset: int = 0) -> None:
        self.old_records_mark = len(self.history) - offset
        self.save_history()

    def wipe_history(self) -> None:
        self.history = []
        self.old_records_mark = 0
        self.save_history()

    def save_history(self) -> None:
        if self.file_path:
            try:
                records_list = []
                for record in self.history:
                    records_list.append(record.to_dict())
                history_json = {
                    "old_records_mark": self.old_records_mark,
                    "records": records_list
                }
                with open(self.file_path, "w") as f:
                    json.dump(history_json, f, indent=4, ensure_ascii=False)
            except IOError as e:
                print(f"Failed to save history. Error: {e}")

    def load_history(self, file_path: str) -> None:
        if file_path:
            try:
                with open(file_path, "r") as f:
                    history_json = json.load(f)
                    self.old_records_mark = history_json["old_records_mark"]
                    records_list = history_json["records"]
                    for record in records_list:
                        self.history.append(HistoryRecord(
                            record["role"],
                            record["message"],
                            datetime.strptime(record["create_time"], "%Y-%m-%d %H:%M:%S"),
                            record["hash"]
                        ))
            except IOError as e:
                print("History file not found. Start anew.")
                self.history = []