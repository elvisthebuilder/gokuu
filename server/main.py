import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Goku Backend API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Server Static Files: Mount assets if dist exists
dist_path = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.exists(dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="static")

@app.get("/config")
async def get_config():
    """Check which API keys are configured (return actual values for UI)."""
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
        "HF_TOKEN": os.getenv("HF_TOKEN", ""),
        "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "GOKU_MODEL": os.getenv("GOKU_MODEL", "default")
    }

@app.post("/config")
async def update_config(config_data: dict):
    """Update .env with new API keys."""
    from server.config_manager import config_manager
    try:
        for key, value in config_data.items():
            config_manager.set_key(key, value)
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Goku Backend is ONLINE", "status": "Dragon Ball Z vibes active"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# Connection Manager for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

import json
import asyncio
from server.lite_router import router
from server.mcp_manager import mcp_manager
from server.memory import memory

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                try:
                    data = await websocket.receive_text()
                    logger.info(f"Received message: {data}")
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        msg = {"type": "message", "content": data}
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    continue

                if msg.get("type") == "stop":
                    logger.info("Received termination signal")
                    await manager.send_personal_message(json.dumps({"type": "status", "content": "Action Terminated"}), websocket)
                    continue

                # Main Processing Block
                from server.agent import agent
                try:
                    user_text = msg.get("content", "")
                    if not user_text: continue

                    async for event in agent.run_agent(user_text):
                        await manager.send_personal_message(json.dumps(event), websocket)
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    await manager.send_personal_message(json.dumps({
                        "type": "error", 
                        "content": str(e)
                    }), websocket)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"Critical error in loop: {str(e)}")
                # Continue the outer loop

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error in websocket loop: {str(e)}")
        await manager.send_personal_message(json.dumps({"type": "error", "content": str(e)}), websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
