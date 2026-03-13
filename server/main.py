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

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enable debug logging for our trace modules
logging.getLogger("WhatsAppBot").setLevel(logging.DEBUG)
logging.getLogger("ChannelManager").setLevel(logging.DEBUG)

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

@app.on_event("startup")
async def startup_event():
    """Start the Telegram and WhatsApp bots in the background."""
    from server.telegram_bot import start_telegram_bot # type: ignore
    from server.whatsapp_bot import run_whatsapp_bot # type: ignore
    
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if tg_token:
        asyncio.create_task(start_telegram_bot(tg_token))
        logger.info("Telegram Bot startup initiated.")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not found. Telegram bot skipped.")
        
    # Start WhatsApp Bot (Runs neonize in a thread)
    loop = asyncio.get_running_loop()
    asyncio.create_task(run_whatsapp_bot(loop))
    logger.info("WhatsApp Bot startup initiated with main loop.")

    # Start DEF Pipeline Poller
    asyncio.create_task(poll_job_tracker())
    logger.info("JobTracker polling loop started.")

async def poll_job_tracker():
    """Background loop to check for pending approvals and scheduled jobs."""
    from server.job_tracker import job_tracker # type: ignore
    from server.agent import agent # type: ignore
    import datetime
    
    while True:
        try:
            now = datetime.datetime.utcnow()
            
            # 1. Check for Pending Approvals
            approvals = job_tracker.get_jobs_by_status(["AWAITING_APPROVAL"])
            for job in approvals:
                # We use reminder_sent as a dirty flag to avoid spamming the user
                if not job.get("reminder_sent"):
                    msg = f"🔔 **Audit Department Proposal**\n\n{job.get('payload', {}).get('plan', 'No plan provided.')}\n\nDo you want to implement this now, or schedule it for later?"
                    # For simplicity, log it or send via broadcast on WS. In a full system, you'd route this to the specific user chat via Telegram/WhatsApp.
                    logger.info(f"[DEF] {msg}")
                    job_tracker.set_reminder_sent(job["job_id"])

            # 2. Check for Scheduled Jobs approaching 5 minutes
            scheduled = job_tracker.get_jobs_by_status(["SCHEDULED"])
            for job in scheduled:
                if job.get("scheduled_for") and not job.get("reminder_sent"):
                    dt = datetime.datetime.fromisoformat(job["scheduled_for"])
                    diff = dt - now
                    if 0 <= diff.total_seconds() <= 300: # Within 5 minutes
                        msg = f"⏳ **Reminder**: Implementation of {job['job_id']} starts in 5 minutes. Proceed or reschedule?"
                        logger.info(f"[DEF] {msg}")
                        job_tracker.set_reminder_sent(job["job_id"])
                        
            # 3. Resume PENDING or Auto-Execute SCHEDULED
            for job in scheduled:
                 if job.get("scheduled_for"):
                    dt = datetime.datetime.fromisoformat(job["scheduled_for"])
                    if now >= dt:
                        logger.info(f"Executing scheduled job: {job['job_id']}")
                        job_tracker.update_job_status(job["job_id"], "RUNNING")
                        asyncio.create_task(agent.run_subagent_background(
                            "department_implement", 
                            "Execute the approved plan.", 
                            str(job.get("payload", {})), 
                            "system", 
                            job["job_id"]
                        ))

        except Exception as e:
            logger.error(f"Error in job poller: {e}")
            
        await asyncio.sleep(60) # Poll every 60 seconds

@app.get("/")
async def root():
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Goku Backend is ONLINE", "status": "Multi-channel active (Telegram/WhatsApp)"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

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
                try:
                    user_text = msg.get("content", "")
                    if not user_text: continue

                    async for event in agent.run_agent(user_text, source="web"):
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
    import uvicorn # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000)
