import os
import re
import uuid
import logging
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient # type: ignore
from qdrant_client.http import models # type: ignore
from .lite_router import router # type: ignore

logger = logging.getLogger(__name__)

# Default persona name for Goku (non-persona sessions)
GOKU_DEFAULT_PERSONA = "goku_default"

def _safe_collection_name(persona_name: str) -> str:
    """Convert a persona name to a valid Qdrant collection name."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", persona_name).strip("_")
    return f"goku_mem_{safe}"


class VectorMemory:
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        # 5s timeout — prevents the agent loop from hanging if Qdrant is offline
        self.client = QdrantClient(url=self.url, check_compatibility=False, timeout=5)
        self.online = False
        # Track existing collections and their vector dimensions
        self._known_collections: Dict[str, int] = {}
        self._check_connectivity()

    def _check_connectivity(self):
        """Verify Qdrant is reachable and index existing collections."""
        try:
            collections = self.client.get_collections().collections
            for col in collections:
                try:
                    info = self.client.get_collection(col.name)
                    if hasattr(info, "config") and hasattr(info.config, "params"):
                        self._known_collections[col.name] = info.config.params.vectors.size
                except Exception:
                    pass
            self.online = True
            logger.debug(f"Memory: Qdrant online. Collections: {list(self._known_collections.keys())}")
        except Exception as e:
            logger.debug(f"Memory: Qdrant offline — {e}")
            self.online = False

    async def _ensure_collection(self, collection_name: str, vector_size: int):
        """Create a Qdrant collection if it doesn't exist yet."""
        if collection_name in self._known_collections:
            return
        try:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )
            self._known_collections[collection_name] = vector_size
            logger.info(f"Memory: Created collection '{collection_name}' (dim={vector_size})")
        except Exception as e:
            logger.error(f"Memory: Failed to create collection '{collection_name}': {e}")
    async def _get_embedding_with_retry(self, text: str, images: Optional[List[str]] = None, max_retries: int = 3) -> List[float]:
        """Fetch embeddings with exponential backoff for network resilience."""
        import asyncio
        for attempt in range(max_retries):
            try:
                return await router.get_embedding(text, images=images)
            except Exception as e:
                # specifically look for connection/DNS errors (litellm or httpx)
                e_str = str(e).lower()
                if "connection" in e_str or "resolution" in e_str or "timeout" in e_str:
                    wait_time = (2 ** attempt)  # 1s, 2s, 4s
                    logger.warning(f"Memory: Embedding failed (attempt {attempt+1}/{max_retries}). Retrying in {wait_time}s... Error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    # For other errors (like invalid API key), don't bother retrying
                    raise e
        # Final attempt
        return await router.get_embedding(text, images=images)

    async def add_memory(
        self,
        text: Optional[str],
        images: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        persona_name: str = GOKU_DEFAULT_PERSONA,
    ):
        """
        Store memory in a persona-scoped Qdrant collection.

        - text: The message or content to embed.
        - images: List of local image file paths (multimodal).
        - file_path: Path to a file (PDF, txt, etc.) to embed its text content.
        - metadata: Arbitrary key-value metadata to store alongside the memory.
        - persona_name: Name of the persona this memory belongs to.
          Each persona gets its own isolated collection with no cross-persona leakage.
        """
        if not self.online or (not text and not images and not file_path):
            return

        collection_name = _safe_collection_name(persona_name)
        safe_text = text or ""

        # --- File embedding: extract text content from documents ---
        if file_path and os.path.exists(file_path):
            try:
                file_content = _extract_file_text(file_path)
                if file_content:
                    safe_text = f"{safe_text}\n\n[File: {os.path.basename(file_path)}]\n{file_content[:4000]}"  # type: ignore[index]
            except Exception as fe:
                logger.warning(f"Memory: Could not extract text from file {file_path}: {fe}")

        try:
            # Generate embedding with retry logic for network resilience
            vector = await self._get_embedding_with_retry(safe_text, images=images)

            # Ensure the persona-scoped collection exists
            await self._ensure_collection(collection_name, len(vector))

            expected_dim = self._known_collections.get(collection_name)
            if expected_dim and len(vector) != expected_dim:
                logger.warning(f"Memory: Dimension mismatch for '{collection_name}' ({len(vector)} vs {expected_dim}). Skipping.")
                return

            self.client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "text": safe_text,
                            "has_images": bool(images),
                            "has_file": bool(file_path),
                            "file_name": os.path.basename(file_path) if file_path else None,
                            "persona": persona_name,
                            "metadata": metadata or {},
                            "timestamp": time.time(),
                        }
                    )
                ]
            )
            log_s = str(safe_text) if safe_text else "multimodal data"
            log_s_short = log_s[:40]  # type: ignore[index]
            logger.debug(f"Memory[{persona_name}]: Indexed '{log_s_short}...'")
        except Exception as e:
            logger.error(f"Memory Error (add) [{persona_name}]: {e}")

    async def search_memory(
        self,
        query: str,
        limit: int = 5,
        persona_name: str = GOKU_DEFAULT_PERSONA,
    ) -> List[Dict[str, Any]]:
        """
        Search a persona-scoped memory collection for the most relevant past context.

        Each persona only searches its own collection — no cross-persona leakage.
        """
        if not self.online or not query.strip():
            return []

        collection_name = _safe_collection_name(persona_name)
        if collection_name not in self._known_collections:
            return []  # No memories stored for this persona yet

        try:
            vector = await self._get_embedding_with_retry(query)
            expected_dim = self._known_collections.get(collection_name)
            if expected_dim and len(vector) != expected_dim:
                return []

            # Flexibly handle different qdrant-client versions
            if hasattr(self.client, "search"):
                results = self.client.search(
                    collection_name=collection_name,
                    query_vector=vector,
                    limit=limit
                )
            elif hasattr(self.client, "query_points"):
                res = self.client.query_points(
                    collection_name=collection_name,
                    query=vector,
                    limit=limit
                )
                results = res.points if hasattr(res, "points") else res
            else:
                logger.error(f"Memory: QdrantClient object ({type(self.client)}) has no known search method.")
                return []

            return [getattr(hit, 'payload', {}) for hit in results if hasattr(hit, 'payload')]
        except Exception as e:
            logger.error(f"Memory Error (search) [{persona_name}]: {e}")
            return []

    async def get_recent_messages(
        self,
        jid: str,
        limit: int = 20,
        persona_name: str = GOKU_DEFAULT_PERSONA
    ) -> List[Dict[str, Any]]:
        """
        Fetch the most recent messages for a specific chat/group JID chronologically.
        Uses Qdrant scroll with metadata filters.
        """
        if not self.online:
            return []

        collection_name = _safe_collection_name(persona_name)
        if collection_name not in self._known_collections:
            return []

        try:
            # Use scroll to fetch points filtered by metadata.group
            results, _ = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.group",
                            match=models.MatchValue(value=jid),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            
            # Sort by timestamp descending (newest first)
            payloads = [getattr(r, 'payload', {}) for r in results if hasattr(r, 'payload')]
            sorted_payloads = sorted(payloads, key=lambda x: x.get("timestamp", 0), reverse=True)
            return sorted_payloads
        except Exception as e:
            logger.error(f"Memory Error (scroll) [{persona_name}]: {e}")
            return []


def _extract_file_text(file_path: str) -> str:
    """Extract plain text from supported file types for embedding."""
    ext = os.path.splitext(file_path)[1].lower()
    text = ""

    if ext in [".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"]:
        with open(file_path, "r", errors="ignore") as f:
            text = f.read()

    elif ext == ".pdf":
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(file_path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            try:
                import PyPDF2  # type: ignore
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join(p.extract_text() or "" for p in reader.pages)
            except Exception:
                pass

    elif ext in [".docx"]:
        try:
            import docx  # type: ignore
            doc = docx.Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            pass

    elif ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".sh", ".html", ".css"]:
        with open(file_path, "r", errors="ignore") as f:
            text = f.read()

    return text.strip()


memory = VectorMemory()
