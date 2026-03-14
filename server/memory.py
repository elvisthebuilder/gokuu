import os
import uuid
import logging
import time
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient # type: ignore
from qdrant_client.http import models # type: ignore
from .lite_router import router # type: ignore

logger = logging.getLogger(__name__)

class VectorMemory:
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        # 5s timeout to prevent hanging the agent loop if Qdrant is down
        self.client = QdrantClient(url=self.url, check_compatibility=False, timeout=5)
        self.collection_name = "goku_memory"
        self.online = False
        self.vector_size: Optional[int] = None
        self._ensure_collection()

    def _ensure_collection(self):
        """Initial connectivity check and collection discovery."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if exists:
                col_info = self.client.get_collection(self.collection_name)
                # Safely extract vector size from existing collection
                if hasattr(col_info, "config") and hasattr(col_info.config, "params"):
                    self.vector_size = col_info.config.params.vectors.size
                self.online = True
                logger.debug(f"Memory: Connected to '{self.collection_name}' (dim={self.vector_size})")
            else:
                self.online = True # We can create on-demand
                logger.debug(f"Memory: '{self.collection_name}' does not exist. Will create on first write.")
        except Exception as e:
            logger.debug(f"Memory offline: {e}")
            self.online = False

    async def _create_collection(self, size: int):
        """Creates the collection with the detected embedding dimensions."""
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
            )
            self.vector_size = size
            logger.info(f"Memory: Created collection with {size} dimensions.")
        except Exception as e:
            logger.error(f"Memory: Failed to create collection: {e}")

    async def add_memory(self, text: Optional[str], images: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None):
        """Add text and/or images to vector memory."""
        if not self.online or (not text and not images):
            return
            
        safe_text = text or ""
        try:
            # Generate multimodal embedding
            vector = await router.get_embedding(safe_text, images=images)
            
            # Sync dimensions
            if self.vector_size is None:
                await self._create_collection(len(vector))
            elif len(vector) != self.vector_size:
                logger.warning(f"Memory dimension mismatch: {len(vector)} != {self.vector_size}")
                return
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "text": safe_text,
                            "has_images": bool(images),
                            "metadata": metadata or {},
                            "timestamp": time.time()
                        }
                    )
                ]
            )
            log_msg = str(safe_text)[:30] if safe_text else "multimodal data"  # type: ignore[index]
            logger.debug(f"Memory: Indexed {log_msg}...")
        except Exception as e:
            logger.error(f"Memory Error (add): {e}")

    async def search_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search memory for relevant previous context."""
        if not self.online or not query.strip():
            return []
            
        try:
            vector = await router.get_embedding(query)
            if self.vector_size is None or len(vector) != self.vector_size:
                return []
            
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit
            )
            return [hit.payload for hit in results]
        except Exception as e:
            logger.error(f"Memory Error (search): {e}")
            return []

memory = VectorMemory()
