import os
from qdrant_client import QdrantClient
from qdrant_client.http import models
from typing import List, Dict, Any
import uuid
import logging

logger = logging.getLogger(__name__)

class VectorMemory:
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.client = QdrantClient(url=self.url)
        self.collection_name = "goku_memory"
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
                )
                logger.info(f"Created collection: {self.collection_name}")
            self.online = True
        except Exception:
            # Silence connection errors when running without Docker
            self.online = False

    async def add_memory(self, text: str, metadata: Dict[str, Any] = None):
        """Add text to vector memory (RAG)."""
        if not hasattr(self, 'online') or not self.online:
            return
            
        try:
            # Dummy vector for demonstration:
            vector = [0.1] * 1536 
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={"text": text, "metadata": metadata or {}}
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Error adding memory: {str(e)}")

    async def search_memory(self, query: str, limit: int = 5):
        """Search relevant context from memory."""
        if not hasattr(self, 'online') or not self.online:
            return []
            
        try:
            # Dummy query vector
            vector = [0.1] * 1536
            
            # Use search if available, fallback to query_points if newer client
            if hasattr(self.client, 'search'):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=vector,
                    limit=limit
                )
            else:
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=vector,
                    limit=limit
                ).points
                
            return [hit.payload for hit in results]
        except Exception as e:
            logger.error(f"Error searching memory: {str(e)}")
            return []

memory = VectorMemory()
