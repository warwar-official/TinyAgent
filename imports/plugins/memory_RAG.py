import os
import json
import time
import numpy as np
import faiss
from typing import Any

class MemoryRAG:
    """
    Implements storage and vector search for model memories using FAISS.
    Optimized for weak devices (CPU-only, no AVX requirements explicitly enforced here but using standard faiss).
    """

    def __init__(self, db_path: str, embedding_function: callable[[str], list[float]]):
        """
        Initialize MemoryRAG.

        Args:
            db_path: Path to the directory or file prefix where the database is stored.
            embedding_function: A function that takes a string and returns a list of floats (vector).
        """
        self.db_path = db_path
        self.embedding_function = embedding_function
        self.index = None
        self.metadata: list[dict[str, Any]] = []
        self.dimension = 0
        
        # Ensure db_path is a directory reference or base path. 
        # If it looks like a file extension, strip it or handle typically.
        # Here we treat db_path as a "base name" or directory. 
        # If user passes "memories", we use "memories.index" and "memories.json".
        
        # Check if we should treat it as a directory or file prefix.
        # User requirement: "If path is empty, create it".
        # If db_path is a directory, we'll use default filenames inside.
        if not db_path:
             raise ValueError("db_path cannot be empty.")

        self.index_path = f"{self.db_path}.index"
        self.metadata_path = f"{self.db_path}.json"

        self._load_db()

    def _load_db(self):
        """Loads the FAISS index and metadata from disk."""
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
        """Initializes a new database."""
        # We don't know the dimension yet until first add or explicit init.
        # But we can't create FAISS index without dimension.
        # We will lazy-init index on first add if dimension is unknown, 
        # OR we assume embedding_function returns a specific size?
        # Safer to lazy init or require dimension hint.
        # Since we use IndexFlatL2, we need d.
        # We'll wait for the first addition to initialize index if it doesn't exist.
        self.index = None
        self.metadata = []
        self.dimension = 0

    def _ensure_index(self, vector_dim: int):
        """Ensures the FAISS index is initialized with the correct dimension."""
        if self.index is None:
            self.dimension = vector_dim
            # IndexFlatL2 is simple, exact search, low memory overhead compared to IVF.
            self.index = faiss.IndexFlatL2(self.dimension)
        elif self.dimension != vector_dim:
            raise ValueError(f"Embedding dimension mismatch. Index expects {self.dimension}, got {vector_dim}.")

    def _save_db(self):
        """Saves the FAISS index and metadata to disk."""
        if self.index:
            faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def search(self, query: str, limit: int = 5, similarity_threshold: float = None) -> list[str]:
        """
        Search for relevant memories.

        Args:
            query: The query string.
            limit: Maximum number of results to return.
            similarity_threshold: Optional threshold for distance (lower is better for L2). 
                                  FAISS L2 returns squared Euclidean distance.
                                  Heuristic: strict match ~0.
        
        Returns:
            List of relevant memory strings.
        """
        if not self.index or len(self.metadata) == 0:
            return []

        vector = np.array([self.embedding_function(query)], dtype='float32')
        distances, indices = self.index.search(vector, limit)

        results = []
        current_time = time.time()

        # FAISS returns -1 for not found/padding
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            dist = distances[0][i]
            
            # Filter by threshold if provided
            # Note: For L2, lower keys are closer. If threshold is "similarity" (often 0-1 in cosine), 
            # we need to know what the user expects.
            # User said "limit of similarity". Usually implies "max distance" for L2 or "min similarity" for Cosine.
            # Assuming threshold is "max distance allowed" for L2.
            if similarity_threshold is not None and dist > similarity_threshold:
                 continue

            # Update stats
            # We need to find the metadata item corresponding to this index ID.
            # Since we use IndexFlat without IDMap, the index ID corresponds to the position in our metadata list
            # IF we keep them in sync perfectly (which we do: add to list, add to index).
            if 0 <= idx < len(self.metadata):
                item = self.metadata[idx]
                item['stats']['total_access'] += 1
                item['stats']['last_access'] = current_time
                results.append(item['text'])
        
        # We modified stats, but we might not want to save on every read for performance?
        # User requirement: "Class has to keep statistics". 
        # User requirement 2.3.2: "Save base after adding".
        # It doesn't explicitly say "after search". 
        # But for persistence, we should probably save periodically or assume the user accepts
        # stats lost on crash if not saved.
        # For data integrity of stats, let's NOT save on every search (IO heavy), 
        # but maybe the user expects it. 
        # Given "weak device" optimization, avoiding write on read is good.
        # We will ONLY save on modifications (add/cleanup).
        
        return results

    def add_memory(self, message: str):
        """
        Adds a new memory to the database.
        
        1. Identical check (very low distance).
        2. Similar check (mid distance) -> Replace.
        3. Unique -> Add.
        """
        vector = np.array([self.embedding_function(message)], dtype='float32')
        self._ensure_index(vector.shape[1])

        # Search for similar existing memories
        # We need to check if there's anything very close.
        # Let's search for top 1.
        D, I = self.index.search(vector, 1)
        
        exists_idx = I[0][0]
        distance = D[0][0]
        
        # Define thresholds (heuristic, depends on embedding model)
        # Using typical values for normalized vectors with L2
        # Identical: < 1e-5 (float precision mostly)
        # Very similar: < 0.2 (heuristic for "close meaning")
        IDENTICAL_THRESHOLD = 1e-4 
        SIMILAR_THRESHOLD = 0.3 # Configurable? keeping simple for now.

        current_time = time.time()
        
        if exists_idx != -1:
            if distance < IDENTICAL_THRESHOLD:
                # 2.3.1.1: Identical -> Ignore
                # Maybe update last access? User says "ignore new".
                return 

            if distance < SIMILAR_THRESHOLD:
                # 2.3.1.2: Very similar -> Replace old
                # Replacing in FAISS IndexFlatL2 is not directly supported without reconstruction 
                # or removing and adding (which changes ID).
                # To maintain "replace" semantics efficiently without ID map:
                # We can't easily "update" a vector in FlatL2 without re-adding.
                # But since we use simple list alignment:
                # We should remove the old one (mark as deleted or actually remove) and add new one?
                # Or just add new one and remove old one logic?
                # FAISS remove_ids requires IndexIDMap. We are using FlatL2 for simplicity/low memory.
                
                # Option A: Just add new, and we will have duplicates? No, that violates requirement.
                # Option B: Rebuild index? Expensive.
                # Option C: Use IndexIDMap from start.
                
                # Let's switch init to use IndexIDMap if we need to remove/replace.
                # But IndexIDMap is memory overhead.
                # Actually, for "weak devices" and "low fragment count", maybe we just use a helper to remove.
                # But for now, since we haven't implemented remove yet, let's see.
                
                # If we "replace", we likely mean "update the text but keep the vector?" 
                # No, if the text is "similar but not same", the vector is also "similar but not same".
                # We want to store the NEW vector and NEW text, replacing the OLD one.
                
                # Implementation for Replace without IDMap:
                # Python list: replace metadata.
                # FAISS: we can't update. We must remove and add.
                # Since we don't have IDMap, we are stuck with strict ordering.
                # 
                # Workaround for generic IndexFlat:
                # We can't remove easily.
                # 
                # Decision: Re-initialize index with all data except the replaced one?
                # If "low amount of fragments" (as per requirements), rebuilding index is fast.
                # Let's assume < 10k items. Rebuilding is milliseconds.
                
                self.metadata[exists_idx]['text'] = message
                self.metadata[exists_idx]['created_at'] = current_time
                self.metadata[exists_idx]['stats']['total_access'] = 0 # Reset stats for new memory? Or keep?
                # "Old necessary to replace". Usually implies updated content.
                # Let's reset stats or keep? safer to keep "last access" but this is a NEW memory technically.
                # Let's keep it simple: It's a "refinement" of the memory.
                
                # Update vector in FAISS?
                # Since we can't update in place, we will rebuild index for simplicity and robustness 
                # on small datasets.
                self._rebuild_index_with_new_vector(exists_idx, vector[0])
                self._save_db()
                return

        # 2.3.1.3: No similar -> Add new
        self.index.add(vector)
        self.metadata.append({
            'id': len(self.metadata), # Virtual ID
            'text': message,
            'created_at': current_time,
            'stats': {'total_access': 0, 'last_access': 0}
        })
        self._save_db()

    def _rebuild_index_with_new_vector(self, index_to_update: int, new_vector):
        """
        Helper to handle 'replacement' by rebuilding index which is fast for small data.
        Updates the vector in the index at `index_to_update`.
        """
        # Read all vectors from current index? IndexFlatL2 stores them.
        # Or just rely on re-embedding all metadata? No, that's expensive (re-embedding).
        # We can reconstruct vectors from the index.
        
        ntotal = self.index.ntotal
        # Reconstruct all vectors
        all_vectors = []
        # IndexFlatL2 allows direct access if we knew how, but safest public API:
        # self.index.reconstruct(i)
        
        for i in range(ntotal):
            if i == index_to_update:
                all_vectors.append(new_vector)
            else:
                vec = self.index.reconstruct(i)
                all_vectors.append(vec)
        
        # Create new index
        self.index = faiss.IndexFlatL2(self.dimension)
        if all_vectors:
            self.index.add(np.array(all_vectors, dtype='float32'))

    def get_all_memories_json(self) -> str:
        """Returns all memories as a JSON string."""
        return json.dumps(self.metadata, ensure_ascii=False, indent=2)

    def cleanup(self, days_old: int, min_requests: int):
        """
        Deletes memories older than N days with fewer than M requests.
        """
        cutoff_time = time.time() - (days_old * 86400)
        
        # Identify indices to keep
        indices_to_keep = []
        new_metadata = []
        
        for i, item in enumerate(self.metadata):
            created_at = item['created_at']
            requests = item['stats']['total_access']
            
            # Logic: Delete if (Older than N) AND (Requests < M)
            # So Keep if (Newer or Equal N) OR (Requests >= M)
            # Wait, "Delete memories older than N ... to which there were less than M requests"
            # -> Condition to Delete: created < cutoff AND requests < min_requests
            
            if created_at < cutoff_time and requests < min_requests:
                # Remove
                continue
            
            indices_to_keep.append(i)
            new_metadata.append(item)
            
        if len(new_metadata) == len(self.metadata):
             return # Nothing to change

        # Rebuild index with only kept vectors
        new_index = faiss.IndexFlatL2(self.dimension)
        for i in indices_to_keep:
            vec = self.index.reconstruct(i)
            new_index.add(np.array([vec], dtype='float32'))
            
        self.index = new_index
        self.metadata = new_metadata
        self._save_db()

