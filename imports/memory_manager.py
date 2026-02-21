from imports.providers_manager import ProvidersManager, Model
from imports.history_manager import HistoryRecord
import numpy as np
import faiss
import os
import json
import time

merge_memmory_prompt = """
Merge this facts into one fact.
Old fact: {}
New fact: {}
Data from new fact prevail over old fact.
Give answer without any comments or own thoughts, only merged fact.
"""

class MemoryManager:
    def __init__(self, config: dict):
        self.providers_manager = ProvidersManager(config["providers"])
        self.emb_model = Model(**config["context"]["memory"]["emb_model"])
        self.merge_model = Model(**config["context"]["memory"]["merge_model"])
        db_path: str = config["context"]["memory"]["db_path"]
        
        if not db_path:
             raise ValueError("db_path cannot be empty.")

        self.index_path = f"{db_path}memory.index"
        self.metadata_path = f"{db_path}memory.json"

        self._load_db()
    
    def search(self, query: str, limit: int = 5, similarity_threshold: float = 0.6) -> list[str]:
        if not self.index or len(self.metadata) == 0:
            return []
        vector = np.array([self.providers_manager.embeding_request(self.emb_model, query)], dtype='float32')
        distances, indices = self.index.search(vector, limit)
        
        results = []
        current_time = time.time()

        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            dist = distances[0][i]
            if similarity_threshold is not None and dist > similarity_threshold:
                 continue
            if 0 <= idx < len(self.metadata):
                item = self.metadata[idx]
                item['stats']['total_access'] += 1
                item['stats']['last_access'] = current_time
                results.append(item['text'])
        self._save_db()
        return results

    def add_memory(self, memory: str):
        IDENTICAL_THRESHOLD = 0.1
        SIMILAR_THRESHOLD = 0.6

        vector = np.array([self.providers_manager.embeding_request(self.emb_model, memory)], dtype='float32')
        self._ensure_index(vector.shape[1])
        
        # Type assertion for Pyright
        assert self.index is not None

        # Check against empty index edge-case
        if self.index.ntotal > 0:
            D, I = self.index.search(vector, 1)
            exists_idx = int(I[0][0])
            distance = float(D[0][0])
        else:
            exists_idx = -1
            distance = float('inf')

        if exists_idx != -1 and distance < SIMILAR_THRESHOLD:
            if distance < IDENTICAL_THRESHOLD:
                return
            
            history_record = HistoryRecord(role="user",message=merge_memmory_prompt.format(self.metadata[exists_idx]["text"], memory))
            try:
                answer = self.providers_manager.generation_request(self.merge_model, [history_record]).strip()
                merged_vector = np.array([self.providers_manager.embeding_request(self.emb_model, answer)], dtype='float32')
            except Exception as e:
                print(f"Error during memory merge: {e}")
                return
            
            # Delete the old element from metadata to shift indices natively
            old_item = self.metadata.pop(exists_idx)
            old_item["text"] = answer
            
            # Use IDSelectorRange to correctly select and remove the corresponding single vector, 
            # causing FAISS to shift following IDs down natively, remaining perfectly in sync with metadata.
            sel = faiss.IDSelectorRange(exists_idx, exists_idx + 1)
            self.index.remove_ids(sel)
            
            # Add the updated memory at the end
            self.metadata.append(old_item)
            self.index.add(merged_vector)
        else:
            # Memory is either the first one or distinct enough to be a new entry
            self.metadata.append({"text": memory, "stats": {"total_access": 0, "last_access": 0}})
            self.index.add(vector)
        self._save_db()

    def get_all_memories_json(self) -> str:
        return json.dumps(self.metadata, ensure_ascii=False, indent=2)

    def _ensure_index(self, vector_dim: int):
        if self.index is None:
            self.dimension = vector_dim
            self.index = faiss.IndexFlatL2(self.dimension)
        elif self.dimension != vector_dim:
            raise ValueError(f"Embedding dimension mismatch. Index expects {self.dimension}, got {vector_dim}.")
    
    def _load_db(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                self.dimension = self.index.d
            except Exception as e:
                print(f"Error loading database: {e}. Starting fresh.")
                self._init_new_db()
        else:
            self._init_new_db()
    
    def _init_new_db(self):
        self.index = None
        self.metadata = []
        self.dimension = 0
    
    def _save_db(self):
        if self.index:
            faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)