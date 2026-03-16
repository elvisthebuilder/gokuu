from qdrant_client import QdrantClient
import os

url = os.getenv("QDRANT_URL", "http://localhost:6333")
print(f"Testing URL: {url}")
try:
    client = QdrantClient(url=url)
    print(f"Client type: {type(client)}")
    print(f"Has search: {hasattr(client, 'search')}")
    # print(f"Dir: {dir(client)}")
except Exception as e:
    print(f"Error: {e}")
