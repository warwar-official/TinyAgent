from qdrant_client import QdrantClient, models
import uuid
import time
import numpy as np
import concurrent.futures
from imports.embedding_service import EmbeddingService

# Shared daemon executor for fire-and-forget KB ingestion (never blocks tool callers)
_KB_INGESTION_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="kb_ingest")

# Similarity Thresholds (Cosine)
DOC_DUPLICATE_THRESHOLD = 0.95
CHUNK_IDENTICAL_THRESHOLD = 0.95
CHUNK_VARIANT_THRESHOLD = 0.90
CHUNK_RELATED_THRESHOLD = 0.85

class KnowledgeBaseRAG:
    """
    RAG engine optimized for knowledge consolidation rather than sequence memory.
    Supports deduplication, variants, and relational graphs for embeddings.
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls, db_path: str = None, embedding_service: EmbeddingService = None) -> 'KnowledgeBaseRAG':
        if cls._instance is None:
            if not db_path or not embedding_service:
                raise ValueError("KnowledgeBaseRAG must be initialized with arguments first.")
            
            import os
            # Prevent Qdrant lock collisions by using a separate directory
            # e.g., turn "./data/memory/db/" into "./data/memory/kbrag_db/"
            base_dir = os.path.dirname(db_path.rstrip("/\\"))
            kb_db_path = os.path.join(base_dir, "kbrag_db") if base_dir else "./data/memory/kbrag_db"
            os.makedirs(kb_db_path, exist_ok=True)
            
            cls._instance = cls(kb_db_path, embedding_service)
        return cls._instance
    
    def __init__(self, db_path: str, embedding_service: EmbeddingService):
        if KnowledgeBaseRAG._instance is not None:
            raise Exception("KnowledgeBaseRAG is a singleton! Use get_instance().")
        self.client = QdrantClient(path=db_path)
        self.embedding_service = embedding_service
        self.vector_size = self.embedding_service.get_vector_size()
        
        self.sources_collection = "kb_sources"
        self.chunks_collection = "kb_chunks"
        
        self._ensure_collections()
        
    def _ensure_collections(self):
        collections = {c.name for c in self.client.get_collections().collections}
        
        for coll_name in [self.sources_collection, self.chunks_collection]:
            if coll_name not in collections:
                self.client.create_collection(
                    collection_name=coll_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        chunks = []
        if not text:
            return chunks
            
        start = 0
        while start < len(text):
            chunks.append(text[start:start + chunk_size].strip())
            start += chunk_size - overlap
        return chunks

    def add_document(self, text: str, url: str = "", title: str = "") -> dict:
        """
        Adds a complete document to the knowledge base.
        Filters duplication at document-level, chunks content, filters internal noise.
        """
        doc_vector = self.embedding_service.embed_single(text)
        
        # Check if doc exists fully
        existing = self.client.query_points(
            collection_name=self.sources_collection,
            query=doc_vector,
            limit=1
        ).points
        
        if existing and existing[0].score >= DOC_DUPLICATE_THRESHOLD:
            return {"status": "skipped", "reason": "duplicate_document"}
            
        source_id = str(uuid.uuid4())
        
        # Store source
        self.client.upsert(
            collection_name=self.sources_collection,
            points=[models.PointStruct(
                id=source_id,
                vector=doc_vector,
                payload={
                    "title": title,
                    "url": url,
                    "added_at": time.time()
                }
            )]
        )
        
        # Chunk text
        chunks_text = self._chunk_text(text)
        if not chunks_text:
            return {"status": "success", "added_chunks": 0}

        chunk_embeddings = self.embedding_service.embed(chunks_text)
        
        # Noise Filtering
        valid_chunks, valid_embeddings = self._filter_noise_chunks(chunks_text, chunk_embeddings)
        
        added_count = 0
        for chunk_txt, chunk_emb in zip(valid_chunks, valid_embeddings):
            if self._insert_chunk(chunk_txt, chunk_emb, source_id):
                added_count += 1
                
        return {"status": "success", "added_chunks": added_count, "source_id": source_id}

    def _filter_noise_chunks(self, chunks: list[str], embeddings: list[np.ndarray]) -> tuple[list[str], list[np.ndarray]]:
        """Removes chunks that are semantically completely unrelated to their source sibling chunks"""
        if len(chunks) <= 5:
            return chunks, embeddings
            
        emb_matrix = np.array(embeddings)
        norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normalized_embs = emb_matrix / norms
        
        sim_matrix = np.dot(normalized_embs, normalized_embs.T)
        
        valid_chunks = []
        valid_embs = []
        
        for i in range(len(chunks)):
            sims = sim_matrix[i].copy()
            sims[i] = -1 # Exclude self
            top_5_sims = np.sort(sims)[-5:]
            avg_sim = float(np.mean(top_5_sims))
            
            # If the chunk has NO strong similarity (> 0.25) to its 5 best sibling chunks, it's noise
            if avg_sim > 0.25:
                valid_chunks.append(chunks[i])
                valid_embs.append(embeddings[i])
                
        return valid_chunks, valid_embs

    def _insert_chunk(self, text: str, vector: np.ndarray, source_id: str) -> bool:
        vec_list = vector.tolist()
        
        existing = self.client.query_points(
            collection_name=self.chunks_collection,
            query=vec_list,
            limit=5
        ).points
        
        # Best match
        best_match = existing[0] if existing else None
        new_chunk_id = str(uuid.uuid4())
        
        if best_match:
            score = best_match.score
            if score >= CHUNK_IDENTICAL_THRESHOLD:
                # Add source_id to existing if not present
                payload = dict(best_match.payload or {})
                if "source_ids" not in payload:
                    payload["source_ids"] = []
                if source_id not in payload["source_ids"]:
                    payload["source_ids"].append(source_id)
                    
                    self.client.upsert(
                        collection_name=self.chunks_collection,
                        points=[models.PointStruct(
                            id=best_match.id,
                            vector=best_match.vector,  # type: ignore (qdrant typing expects dict or list, retrieve returns dict or list)
                            payload=payload
                        )]
                    )
                return False  # Existing identical match absorbed it
            
            elif score >= CHUNK_RELATED_THRESHOLD:
                new_payload = {
                    "text": text,
                    "source_ids": [source_id],
                    "variants": [],
                    "related": []
                }
                
                # Cross-link
                for match in existing:
                    if match.score >= CHUNK_VARIANT_THRESHOLD:
                        new_payload["variants"].append(str(match.id))
                        self._add_to_list(str(match.id), "variants", new_chunk_id)
                    elif match.score >= CHUNK_RELATED_THRESHOLD:
                        new_payload["related"].append(str(match.id))
                        self._add_to_list(str(match.id), "related", new_chunk_id)
                
                self.client.upsert(
                    collection_name=self.chunks_collection,
                    points=[models.PointStruct(
                        id=new_chunk_id,
                        vector=vec_list,
                        payload=new_payload
                    )]
                )
                return True
                
        # Pure insert
        self.client.upsert(
            collection_name=self.chunks_collection,
            points=[models.PointStruct(
                id=new_chunk_id,
                vector=vec_list,
                payload={
                    "text": text,
                    "source_ids": [source_id],
                    "variants": [],
                    "related": []
                }
            )]
        )
        return True

    def _add_to_list(self, point_id: str, list_name: str, value: str):
        res = self.client.retrieve(self.chunks_collection, [point_id], with_vectors=True)
        if not res: return
        point = res[0]
        payload = dict(point.payload or {})
        
        if list_name not in payload:
            payload[list_name] = []
            
        if value not in payload[list_name]:
            payload[list_name].append(value)
            
            # Since vector can be list or dict, Qdrant Python handles it natively
            self.client.upsert(
                collection_name=self.chunks_collection,
                points=[models.PointStruct(
                    id=point.id,
                    vector=point.vector, # type: ignore
                    payload=payload
                )]
            )

    def add_document_async(self, text: str, url: str = "", title: str = "") -> concurrent.futures.Future:
        """
        Submits add_document() to the background executor and returns immediately.
        The caller is never blocked by chunking, embedding, or KNN operations.
        """
        return _KB_INGESTION_EXECUTOR.submit(self.add_document, text, url, title)

    def search(self, query: str, top_k: int = 5, limit_source_id: str = None) -> list[dict]:
        """
        Retrieves matching chunks. Resolves 'variants' by dropping any chunk 
        if its variant partner was already included in higher ranks.
        """
        query_vector = self.embedding_service.embed_single(query)
        
        q_filter = None
        if limit_source_id:
            q_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_ids",
                        match=models.MatchValue(value=limit_source_id)
                    )
                ]
            )
            
        results = self.client.query_points(
            collection_name=self.chunks_collection,
            query=query_vector,
            query_filter=q_filter,
            limit=top_k * 4  # Expanded search margin
        ).points
        
        final_results = []
        seen_variants = set()
        
        for p in results:
            pid = str(p.id)
            if pid in seen_variants:
                continue
                
            payload = p.payload or {}
            variants = payload.get("variants", [])
            
            # Add self and all variants to seen list
            seen_variants.add(pid)
            for v in variants:
                seen_variants.add(v)
                
            final_results.append({
                "id": pid,
                "text": payload.get("text", ""),
                "score": p.score,
                "source_ids": payload.get("source_ids", [])
            })
            
            if len(final_results) >= top_k:
                break
                
        return final_results
