from typing import Any
import os
import uuid

from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding

from imports.mcp.base import MCPServer

# Reuse the HTML parser from the existing web_fetch tool
from imports.tools.web_fetch import PageContentParser
import requests

COLLECTION_NAME = "retrieval_docs"
DEFAULT_CHUNK_SIZE = 500  # approximate characters per chunk


class RetrievalMCP(MCPServer):
    """MCP server for document retrieval (RAG over files and URLs).

    Shares the **same** ``QdrantClient`` and ``TextEmbedding`` instances
    with ``MemoryRAG`` (passed in at construction) but stores data in a
    separate collection (``retrieval_docs``).
    """

    def __init__(self, client: QdrantClient, embedding_model: TextEmbedding) -> None:
        self._client = client
        self._embedding_model = embedding_model
        self._ensure_collection()

    # ------------------------------------------------------------------
    # Collection setup
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        collections = [c.name for c in self._client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            sample_vec = list(self._embedding_model.embed(["test"]))[0]
            vector_size = len(sample_vec)
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

    # ------------------------------------------------------------------
    # RPC handlers
    # ------------------------------------------------------------------

    def _rpc_tool_list(self, params: dict) -> list[dict]:
        return [
            {
                "name": "add_knowledge_file",
                "description": "Add a local file to the retrieval knowledge base. The file is chunked and indexed.",
                "parameters": {
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to index.",
                        }
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "add_knowledge_url",
                "description": "Download a web page and add its text content to the retrieval knowledge base.",
                "parameters": {
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the page to index.",
                        }
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "retrieve_knowledge",
                "description": "Search the retrieval knowledge base and return the most relevant text chunks.",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query.",
                        },
                        "k": {
                            "type": "integer",
                            "description": "Number of results to return.",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    def _rpc_tool_execute(self, params: dict) -> dict:
        name: str = params["name"]
        arguments: dict = params.get("arguments", {})

        dispatch = {
            "add_knowledge_file": self._add_knowledge_file,
            "add_knowledge_url": self._add_knowledge_url,
            "retrieve_knowledge": self._retrieve_knowledge,
        }

        handler = dispatch.get(name)
        if handler is None:
            return {
                "tool_name": name,
                "tool_arguments": arguments,
                "tool_result": None,
                "truncate": False,
                "error": f"Unknown retrieval tool: {name}",
            }
        try:
            return handler(**arguments)
        except Exception as e:
            return {
                "tool_name": name,
                "tool_arguments": arguments,
                "tool_result": None,
                "truncate": False,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _add_knowledge_file(self, path: str) -> dict:
        result = {"tool_name": "add_knowledge_file", "tool_arguments": {"path": path},
                  "tool_result": None, "truncate": False, "error": None}
        if not os.path.isfile(path):
            result["error"] = f"File not found: {path}"
            return result

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        chunks = self._chunk_text(text)
        self._index_chunks(chunks, source=path)
        result["tool_result"] = f"Indexed {len(chunks)} chunks from {path}"
        return result

    def _add_knowledge_url(self, url: str) -> dict:
        result = {"tool_name": "add_knowledge_url", "tool_arguments": {"url": url},
                  "tool_result": None, "truncate": False, "error": None}
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,uk;q=0.8",
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            result["error"] = f"Failed to fetch URL: {e}"
            return result

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            parser = PageContentParser()
            parser.feed(response.text)
            text = " ".join(parser.text_content)
        else:
            text = response.text

        chunks = self._chunk_text(text)
        self._index_chunks(chunks, source=url)
        result["tool_result"] = f"Indexed {len(chunks)} chunks from {url}"
        return result

    def _retrieve_knowledge(self, query: str, k: int = 5) -> dict:
        result = {"tool_name": "retrieve_knowledge", "tool_arguments": {"query": query, "k": k},
                  "tool_result": None, "truncate": False, "error": None}

        query_vector = list(self._embedding_model.embed([query]))[0].tolist()
        points = self._client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=k,
        ).points

        texts = []
        for point in points:
            payload = point.payload or {}
            texts.append(payload.get("text", ""))

        result["tool_result"] = texts
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
        """Split *text* into chunks of approximately *chunk_size* chars.

        Tries to break on paragraph boundaries first (double newline),
        then on single newlines, falling back to hard splits.
        """
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) + 2 <= chunk_size:
                current = f"{current}\n\n{para}" if current else para
            else:
                if current:
                    chunks.append(current)
                # If a single paragraph is larger than chunk_size, split further
                if len(para) > chunk_size:
                    lines = para.split("\n")
                    current = ""
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if len(current) + len(line) + 1 <= chunk_size:
                            current = f"{current}\n{line}" if current else line
                        else:
                            if current:
                                chunks.append(current)
                            # Hard split for very long lines
                            while len(line) > chunk_size:
                                chunks.append(line[:chunk_size])
                                line = line[chunk_size:]
                            current = line
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks

    def _index_chunks(self, chunks: list[str], source: str = "") -> None:
        """Embed and store *chunks* in the Qdrant collection."""
        if not chunks:
            return

        vectors = list(self._embedding_model.embed(chunks))

        points = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            points.append(models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vec.tolist(),
                payload={
                    "text": chunk,
                    "source": source,
                    "chunk_index": i,
                },
            ))

        self._client.upsert(collection_name=COLLECTION_NAME, points=points)
