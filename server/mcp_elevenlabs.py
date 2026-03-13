import os
import httpx # type: ignore
import uvicorn # type: ignore
from fastapi import FastAPI, HTTPException # type: ignore
from pydantic import BaseModel # type: ignore
from typing import Optional, Dict, Any, List
import logging
import importlib
from dotenv import load_dotenv # type: ignore

# Ensure .env is loaded from the project root
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(ENV_PATH, override=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCP-ElevenLabs")

logger.info(f"Loading environment from: {ENV_PATH}")
logger.info(f"ELEVENLABS_API_KEY found: {bool(os.getenv('ELEVENLABS_API_KEY'))}")

app = FastAPI(title="Goku ElevenLabs MCP", version="1.0.0")

class ToolCall(BaseModel):
    name: str
    arguments: dict

# In-memory cache for voices
_voice_cache: Dict[str, Any] = {}

@app.get("/tools")
async def get_tools():
    """Returns the tool definitions for voice management."""
    return [
        {
            "name": "list_voices",
            "description": "List all available ElevenLabs voices with their names, IDs, and descriptions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "set_active_voice",
            "description": "Set the active voice ID to be used for Text-to-Speech replies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voice_id": {
                        "type": "string",
                        "description": "The ID of the ElevenLabs voice to use."
                    }
                },
                "required": ["voice_id"]
            }
        },
        {
            "name": "debug_environment",
            "description": "Check if the Voice MCP server can see the ElevenLabs API keys and configuration.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ]

@app.post("/call")
async def call_tool(tool_call: ToolCall):
    """Executes a voice management tool."""
    # Refresh import cache to detect any hot-installed libraries
    importlib.invalidate_caches()
    # Hot-reload environment before each call to pick up changes without restart
    load_dotenv(ENV_PATH, override=True)
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        return {"error": "ELEVENLABS_API_KEY is not configured in the environment."}

    headers = {
        "xi-api-key": api_key,
        "Accept": "application/json"
    }

    if tool_call.name == "list_voices":
        # Check cache first (cache for 1 hour ideally, but keep it simple for now)
        if _voice_cache.get("voices"):
            logger.info("Returning voices from cache")
            return _voice_cache["voices"]
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://api.elevenlabs.io/v1/voices", headers=headers)
                if resp.status_code == 200:
                    voices_data = resp.json().get("voices", [])
                    result = {
                        "voices": [
                            {
                                "id": v.get("voice_id"),
                                "name": v.get("name"),
                                "labels": v.get("labels", {})
                            }
                            for v in voices_data
                        ]
                    }
                    # Update cache
                    _voice_cache["voices"] = result
                    return result
                else:
                    return {"error": f"API Error: {resp.text}"}
        except Exception as e:
            return {"error": f"Failed to list voices: {str(e)}"}

    elif tool_call.name == "set_active_voice":
        voice_input = tool_call.arguments.get("voice_id")
        if not voice_input:
            raise HTTPException(status_code=400, detail="voice_id is required")
        
        voice_id = voice_input
        
        # Smart Lookup: If the user provided a name, try to find the ID in cache
        if _voice_cache.get("voices"):
            for v in _voice_cache["voices"]["voices"]:
                if voice_input.lower() == v["name"].lower():
                    voice_id = v["id"]
                    logger.info(f"Resolved voice name '{voice_input}' to ID '{voice_id}' via cache")
                    break
        
        # We update the .env file indirectly via a message.
        # Ideally, we edit .env here, but it's cleaner to just update it directly
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        try:
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
            
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("ELEVENLABS_VOICE_ID="):
                    new_lines.append(f"ELEVENLABS_VOICE_ID={voice_id}\n")
                    found = True
                else:
                    new_lines.append(line)
            
            if not found:
                new_lines.append(f"\nELEVENLABS_VOICE_ID={voice_id}\n")
                
            with open(env_path, "w") as f:
                f.writelines(new_lines)
                
            logger.info(f"Updated ELEVENLABS_VOICE_ID to {voice_id}")
            return {"success": True, "message": f"Successfully set active voice to {voice_id}. Change applied immediately (Hot-Reloaded)."}
        except Exception as e:
            return {"error": f"Failed to save to .env: {str(e)}"}

    elif tool_call.name == "debug_environment":
        return {
            "status": "diagnostic",
            "env_path": ENV_PATH,
            "env_exists": os.path.exists(ENV_PATH),
            "api_key_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
            "current_voice_id": os.getenv("ELEVENLABS_VOICE_ID"),
            "suggestion": "Configuration is hot-reloaded before every tool call. No restart required."
        }
            
    raise HTTPException(status_code=404, detail=f"Tool {tool_call.name} not found")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8083))
    uvicorn.run(app, host="0.0.0.0", port=port)
