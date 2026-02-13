from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from hashlib import md5

@dataclass
class HistoryRecord:
    id: str
    create_time: datetime
    role: str
    message: str

class HistoryManager:
    def __init__(self, history_path: Path|None = None) -> None:
        self.history: list[HistoryRecord] = []
        if history_path:
            self.load_history(history_path)

    def add_record(self, role: str, message: str) -> None:
        creation_date = datetime.now()
        record_id = md5((creation_date.strftime("%S") + role + message).encode()).hexdigest()
        new_record = HistoryRecord(record_id, creation_date, role, message)
        self.history.append(new_record)
    
    def get_records(self, count: int = 0) -> list[HistoryRecord]:
        records_list = self.history[0 - count:]
        return records_list

    def remove_record(self, record_id: str) -> None:
        for record in self.history:
            if record.id == record_id:
                self.history.remove(record)
                break
    
    def update_record(self, record_id: str, message: str) -> None:
        for record in self.history:
            if record.id == record_id:
                record.message = message
                break

    def load_history(self, file_path: Path) -> None:
        raise NotImplementedError

if __name__ == "__main__":
    history = HistoryManager()
    history.add_record("user","test1")
    history.add_record("model","test2")
    history.add_record("user","test3")
    history.add_record("model","test4")
    print(history.get_records(2))
    print(history.get_records())
    print(history.get_records(5))