from imports.providers_manager import ProvidersManager, Model
from imports.history_manager import HistoryRecord
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding
import json
import time
import os
import uuid
from typing import Any

merge_memory_prompt = """
Merge the following two facts into a single, concise sentence.
Old fact: {old_fact}
New fact: {new_fact}

Rule: If there is a contradiction, the 'New fact' strictly overrides the 'Old fact'. 
Output EXACTLY and ONLY the final merged sentence. Do not add any conversational filler, explanations, or prefixes like 'Merged fact:'.
"""

COLLECTION_NAME = "memories"
IDENTICAL_THRESHOLD = 0.97  # cosine: 1.0 = identical
SIMILAR_THRESHOLD = 0.85    # cosine: high overlap warrants merging


class MemoryRAG:
    def __init__(self, config: dict):
        self.providers_manager = ProvidersManager(config["providers"])
        self.merge_model = Model(**config["context"]["memory"]["merge_model"])

        rag_config: dict = config["context"]["memory"]
        db_path: str = rag_config["db_path"]
        models_cache_path: str = rag_config["models_cache_path"]
        emb_model_name: str = rag_config["emb_model_name"]

        if not db_path:
            raise ValueError("db_path cannot be empty.")

        os.makedirs(db_path, exist_ok=True)
        os.makedirs(models_cache_path, exist_ok=True)

        # Initialize fastembed with cache in the app folder
        self.embedding_model = TextEmbedding(
            model_name=emb_model_name,
            cache_dir=models_cache_path
        )

        # Initialize Qdrant in on-disk local mode
        self.client = QdrantClient(path=db_path)
        self._ensure_collection()

    def search(
        self,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.6,
        filters: dict | None = None
    ) -> list[str]:
        """Search memories by semantic similarity with optional metadata filters.

        Args:
            query: Text to search for.
            limit: Maximum number of results.
            similarity_threshold: Minimum cosine similarity (0..1). Lower = stricter.
            filters: Optional dict of metadata filters. Each key-value pair becomes a
                     FieldCondition. Use a plain value for exact match, or a dict with
                     'gte'/'lte'/'gt'/'lt' keys for range filters.
                     Examples:
                         {"source": "conversation"}
                         {"total_access": {"gte": 5}}
                         {"type": "fact", "source": "autonomous"}
        """
        query_filter = self._build_filter(filters) if filters else None
        query_vector = list(self.embedding_model.embed([query]))[0].tolist()

        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=similarity_threshold,
        ).points

        texts: list[str] = []
        current_time = time.time()
        updates: list[tuple[Any, int]] = []  # (point_id, new_total_access)

        for point in results:
            payload = point.payload or {}
            new_access = int(payload.get("total_access", 0)) + 1
            texts.append(str(payload.get("text", "")))
            updates.append((point.id, new_access))

        # Batch-update access stats
        for point_id, total_access in updates:
            self.client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"total_access": total_access, "last_access": current_time},
                points=[point_id],
            )

        return texts

    def add_memory(self, memory: str, source: str = "", memory_type: str = "") -> None:
        """Add a new memory. Skips near-identical, merges similar, or inserts new.

        Args:
            memory: The text content of the memory.
            source: Origin of the memory (e.g. "conversation", "autonomous").
            memory_type: Category of the memory (e.g. "fact", "preference").
        """
        vector = list(self.embedding_model.embed([memory]))[0].tolist()

        # Check for near-duplicates
        existing = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=1,
        ).points

        if existing:
            top = existing[0]
            score = top.score if top.score is not None else 0.0

            if score > IDENTICAL_THRESHOLD:
                # Near-identical — skip
                return

            if score > SIMILAR_THRESHOLD:
                # Similar — merge via LLM
                old_text = (top.payload or {}).get("text", "")
                history_record = HistoryRecord(
                    role="user",
                    message=merge_memory_prompt.format(old_fact=old_text, new_fact=memory)
                )
                try:
                    merged_text = self.providers_manager.generation_request(
                        self.merge_model, [history_record]
                    ).strip()
                    merged_vector = list(self.embedding_model.embed([merged_text]))[0].tolist()
                except Exception as e:
                    print(f"Error during memory merge: {e}")
                    return

                # Update the existing point with merged content
                updated_payload = dict(top.payload or {})
                updated_payload["text"] = merged_text

                self.client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=[models.PointStruct(
                        id=top.id,
                        vector=merged_vector,
                        payload=updated_payload,
                    )]
                )
                return

        # New distinct memory
        point_id = str(uuid.uuid4())
        payload = {
            "text": memory,
            "time_created": time.time(),
            "source": source,
            "type": memory_type,
            "total_access": 0,
            "last_access": 0,
        }

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )]
        )

    def get_all_memories_json(self) -> str:
        """Returns all stored memories as a JSON string."""
        all_points = []
        offset = None

        while True:
            result = self.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points, next_offset = result
            all_points.extend(p.payload for p in points if p.payload)
            if next_offset is None:
                break
            offset = next_offset

        return json.dumps(all_points, ensure_ascii=False, indent=2)

    def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            # Get vector size from the embedding model
            sample_vec = list(self.embedding_model.embed(["test"]))[0]
            vector_size = len(sample_vec)

            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

    @staticmethod
    def _build_filter(filters: dict) -> models.Filter:
        """Build a Qdrant Filter from a plain dict.

        Exact match:  {"source": "conversation"}
        Range:        {"total_access": {"gte": 5, "lte": 100}}
        """
        conditions: list[models.Condition] = []

        for key, value in filters.items():
            if isinstance(value, dict):
                # Range filter
                conditions.append(models.FieldCondition(
                    key=key,
                    range=models.Range(
                        gte=value.get("gte"),
                        lte=value.get("lte"),
                        gt=value.get("gt"),
                        lt=value.get("lt"),
                    ),
                ))
            else:
                # Exact match
                conditions.append(models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                ))

        return models.Filter(must=conditions)
