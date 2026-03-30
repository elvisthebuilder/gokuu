import os
import sys

# Add the project root to sys.path to allow imports like 'from server.xxx'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi.responses import FileResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from dotenv import load_dotenv # type: ignore
import logging
import asyncio
import json
from contextlib import asynccontextmanager

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Enable debug logging for our trace modules
logging.getLogger("WhatsAppBot").setLevel(logging.DEBUG)
logging.getLogger("ChannelManager").setLevel(logging.DEBUG)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    logger.info("Goku Web Backend is starting. Assuming bots are run via Gateway.")
    
    # We yield to allow the application to run.
    # The actual bots and poll_job_tracker are now handled by server/gateway.py
    yield

app = FastAPI(title="Goku Backend API", version="2.5.0", lifespan=lifespan)

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
    from server.config_manager import config_manager # type: ignore
    from server.whatsapp_bot import whatsapp_bot # type: ignore
    
    config_data = config_manager.get_config()
    # Add integration status
    config_data["WHATSAPP_CONNECTED"] = whatsapp_bot.is_connected
    return config_data

@app.post("/config")
async def update_config(config_data: dict):
    """Update .env with new API keys."""
    from server.config_manager import config_manager # type: ignore
    try:
        for key, value in config_data.items():
            config_manager.set_key(key, value)
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- History Endpoints ---

@app.get("/sessions")
async def get_sessions():
    """Get all past chat sessions."""
    from server.history_manager import history_manager # type: ignore
    return history_manager.get_sessions()

@app.get("/sessions/{session_id}")
async def get_session_messages(session_id: str):
    """Get all messages for a specific session."""
    from server.history_manager import history_manager # type: ignore
    return history_manager.get_messages(session_id)

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    from server.history_manager import history_manager # type: ignore
    history_manager.delete_session(session_id)
    return {"status": "success"}

# --- Persona Endpoints ---

@app.get("/personas")
async def list_personas():
    """List all custom personalities."""
    from server.personality_manager import personality_manager # type: ignore
    return personality_manager.list_personalities()

@app.get("/personas/{name}")
async def get_persona(name: str):
    """Get content of a personality."""
    from server.personality_manager import personality_manager # type: ignore
    content = personality_manager.get_personality_text(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"name": name, "content": content}

@app.post("/personas")
async def save_persona(persona: dict):
    """Save or update personality."""
    from server.personality_manager import personality_manager # type: ignore
    name = persona.get("name")
    content = persona.get("content")
    if not name or not content:
        raise HTTPException(status_code=400, detail="Name and content required")
    success = personality_manager.save_personality(name, content)
    return {"status": "success" if success else "error"}

@app.delete("/personas/{name}")
async def delete_persona(name: str):
    """Delete a personality."""
    from server.personality_manager import personality_manager # type: ignore
    personality_manager.delete_personality(name)
    return {"status": "success"}

# --- Skills & Tools Endpoints ---

@app.get("/skills")
async def list_skills():
    """List all available tools/capabilities."""
    from server.mcp_manager import mcp_manager # type: ignore
    tools = mcp_manager.get_tools()
    # Format tools for UI
    formatted_skills = []
    for tool in tools:
        formatted_skills.append({
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "parameters": tool["function"]["parameters"]
        })
    return formatted_skills

    # The poll_job_tracker logic was moved to server/gateway.py
@app.get("/")
async def root():
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Goku Backend is ONLINE", "status": "Multi-channel active (Telegram/WhatsApp)"}

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

from server.lite_router import router # type: ignore
from server.mcp_manager import mcp_manager # type: ignore
from server.memory import memory # type: ignore

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
                from server.agent import agent # type: ignore
                from server.history_manager import history_manager # type: ignore
                try:
                    user_text = msg.get("content", "")
                    session_id = msg.get("session_id", "default_web") # Frontend should provide this
                    if not user_text: continue

                    # Save user message
                    history_manager.add_message(session_id, "user", user_text)

                    # Restore history to agent if empty (server restart or context switch)
                    if session_id not in agent.histories or not agent.histories[session_id]:
                        logger.info(f"Restoring context for session {session_id} from database...")
                        db_messages = history_manager.get_messages(session_id)
                        agent.histories[session_id] = [{"role": m["role"], "content": m["content"]} for m in db_messages if m["role"] != "user" or m["content"] != user_text]
                        # Note: we exclude the current user_text as run_agent handles it

                    full_response = []
                    logger.info(f"Invoking agent for session {session_id}...")
                    async for event in agent.run_agent(user_text, source="web", session_id=session_id):
                        if event["type"] == "message":
                            full_response.append(event["content"])
                        await manager.send_personal_message(json.dumps(event), websocket)
                    logger.info(f"Agent finished for session {session_id}. Yielded {len(full_response)} message chunks.")
                    
                    # Save assistant response
                    if full_response:
                        history_manager.add_message(session_id, "agent", "".join(full_response))
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
    import uvicorn # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000)
