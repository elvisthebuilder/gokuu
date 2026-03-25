import logging
import asyncio
import os
import re as re_
from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime
from .agent import agent # type: ignore

logger = logging.getLogger("ChannelManager")

class ChannelBroker:
    """Unified broker to handle debouncing, grouping, and agent execution across Telegram, WhatsApp, etc."""
    
    def __init__(self):
        # {session_id: {full_query: str, items: [], timer: Task, source: str, send_fn: Callable}}
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._busy_sessions: set = set()
        self.debounce_seconds = 2.0
        # {source_name: {"send": send_fn, "list_groups": list_fn}}
        self._interfaces: Dict[str, Dict[str, Any]] = {}

    def register_interface(self, source: str, send_fn: Callable[[str, str], Awaitable[Any]], group_lister: Optional[Callable[[], Awaitable[List[Dict[str, str]]]]] = None, info_lister: Optional[Callable[[str], Awaitable[Dict[str, Any]]]] = None):
        """Register a bot's sending, listing, and info-fetching capabilities."""
        self._interfaces[source] = {
            "send": send_fn,
            "list_groups": group_lister,
            "get_chat_info": info_lister
        }
        logger.info(f"Registered interface for {source}")

    async def get_groups(self, source: str) -> List[Dict[str, str]]:
        """List groups for a specific source."""
        if source in self._interfaces:
            lister = self._interfaces[source].get("list_groups")
            if lister:
                return await lister()
        return []

    async def get_chat_info(self, source: str, jid: str) -> Dict[str, Any]:
        """Fetch detailed info for a specific chat/group."""
        if source in self._interfaces:
            lister = self._interfaces[source].get("get_chat_info")
            if lister:
                return await lister(jid)
        return {"status": "error", "message": f"Info fetching not supported for {source}"}

    async def send_message(self, source: str, jid: str, text: str) -> bool:
        """Send a message to a specific JID (user or group) via the registered source interface."""
        if source not in self._interfaces:
            logger.error(f"Cannot send message for {source}: no interface registered.")
            return False
        send_fn = self._interfaces[source].get("send")
        if not send_fn:
            logger.error(f"No send function registered for {source}.")
            return False
        try:
            await send_fn(jid, text)
            logger.info(f"[BROKER] Sent message to {jid} via {source}")
            return True
        except Exception as e:
            logger.error(f"[BROKER] Failed to send to {jid} via {source}: {e}")
            return False


    async def trigger_autonomous_agent(self, source: str, session_id: str, prompt: str, group_name: Optional[str] = None):
        """Trigger the agent proactively (without an incoming message)."""
        if source not in self._interfaces:
            logger.error(f"Cannot trigger autonomous agent for {source}: No interface registered.")
            return

        send_fn = self._interfaces[source]["send"]
        
        # Prepend group context if available
        if group_name:
            prompt = f"[GROUP: {group_name}] {prompt}"
        
        # We wrap the send_fn to match the (text) signature expected by _run_agent_for_session
        async def wrapped_send(text: str):
            await send_fn(session_id, text)

        req = {
            "full_query": prompt,
            "source": source,
            "send_message_fn": wrapped_send,
            "status_update_fn": None,
            "react_fn": None,
            "is_group": True, # Scheduled tasks are usually group-centric
            "attachments": []
        }
        
        # Wait if session is busy
        wait_count = 0
        while session_id in self._busy_sessions:
            if wait_count >= 120: return
            await asyncio.sleep(0.5)
            wait_count += 1

        logger.info(f"[BROKER] Triggering autonomous agent for {source}:{session_id}")
        await self._run_agent_for_session(session_id, req)

    async def handle_incoming_message(
        self, 
        session_id: str, 
        content: str, 
        source: str,
        send_message_fn: Callable[[str], Awaitable[Any]],
        status_update_fn: Optional[Callable[[str], Awaitable[Any]]] = None,
        react_fn: Optional[Callable[[str], Awaitable[Any]]] = None,
        is_voice: bool = False,
        attachment_path: Optional[str] = None,
        is_group: bool = False
    ):
        """Buffers incoming messages and triggers the agent after the debounce window."""
        logger.debug(f"[BROKER TRACE] handle_incoming_message: session={session_id}, source={source}, busy={session_id in self._busy_sessions}")
        
        if session_id not in self._pending_requests:
            self._pending_requests[session_id] = {
                "full_query": "",
                "is_voice": is_voice,
                "attachments": [],
                "source": source,
                "send_message_fn": send_message_fn,
                "status_update_fn": status_update_fn,
                "react_fn": react_fn,
                "is_group": is_group,
                "timer": None
            }
        
        req = self._pending_requests[session_id]
        
        # Combine text content
        if content:
            req["full_query"] = (req["full_query"] + " " + content).strip()
        
        # Track attachments
        if attachment_path:
            req["attachments"].append(attachment_path)
            # Use specific tags to help the agent's native parsers
            ext = os.path.splitext(attachment_path)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
                req["full_query"] += f" [Photo Received: {attachment_path}]"
            else:
                req["full_query"] += f" [File Received: {attachment_path}]"
        
        # Update voice status
        if is_voice:
            req["is_voice"] = True

        # Reset or start debounce timer
        if req["timer"]:
            req["timer"].cancel()
            
        req["timer"] = asyncio.create_task(self._process_after_delay(session_id))
        logger.debug(f"[BROKER TRACE] Timer (re)started for {session_id}")

    async def _process_after_delay(self, session_id: str):
        """Internal debounce wait."""
        try:
            logger.debug(f"[BROKER TRACE] _process_after_delay waiting for {session_id}")
            await asyncio.sleep(self.debounce_seconds)
            
            # Wait if session is busy (with 60s absolute timeout safety)
            wait_count = 0
            while session_id in self._busy_sessions:
                if wait_count >= 120:  # 120 * 0.5s = 60s
                    logger.warning(f"[BROKER TRACE] Deadlock protection: {session_id} has been busy for >60s. Skipping this message.")
                    return
                if wait_count % 10 == 0:
                    logger.debug(f"[BROKER TRACE] {session_id} is busy, waiting...")
                await asyncio.sleep(0.5)
                wait_count += 1
                
            if session_id not in self._pending_requests:
                logger.debug(f"[BROKER TRACE] Request for {session_id} disappeared from pending (cancelled?)")
                return
                
            req = self._pending_requests.pop(session_id)
            logger.debug(f"[BROKER TRACE] Triggering agent for {session_id}")
            await self._run_agent_for_session(session_id, req)
            
        except asyncio.CancelledError:
            logger.debug(f"[BROKER TRACE] Timer cancelled for {session_id}")
            pass
        except Exception as e:
            logger.error(f"Error in debounce loop for {session_id}: {e}")

    async def _run_agent_for_session(self, session_id: str, req: Dict[str, Any]):
        """Executes the agent and routes responses back to the source."""
        self._busy_sessions.add(session_id)
        
        full_query = req["full_query"]
        source = req["source"]
        send_fn = req["send_message_fn"]
        status_fn = req["status_update_fn"]
        react_fn = req["react_fn"]
        is_voice = req["is_voice"]
        is_group_chat = req.get("is_group", False)

        logger.info(f"[BROKER TRACE] Starting agent for {session_id}. Query: {full_query[:50]}...")

        try:
            # 1. Status Update (Thinking...)
            if status_fn:
                status_text = "🤔 Thinking..."
                if is_voice:
                    status_text = "🎙️ Processing your voice..."
                elif req["attachments"]:
                    status_text = "⏳ Analyzing your content..."
                
                # Note: The status_fn should handle creating/editing the status message
                # For Telegram, this is often the response to wait for.
                await status_fn(status_text)

            # 2. Run Agent
            response_text: str = ""
            current_buffer: str = ""
            gen = agent.run_agent(full_query, source=source, session_id=session_id, react_fn=react_fn, is_group=is_group_chat)
            
            try:
                async for event in gen:
                    logger.debug(f"[BROKER TRACE] Agent event: {event.get('type')}")
                    
                    if event["type"] == "message":
                        chunk = event["content"]
                        if chunk:
                            # Clean any residual thought tags just in case
                            chunk = re_.sub(r'<(thought|think)>.*?(</\1>|$)', '', chunk, flags=re_.DOTALL).strip()
                            if chunk:
                                response_text = f"{response_text}\n\n{chunk}" if response_text else chunk
                                current_buffer = f"{current_buffer}{chunk}"
                                
                                # STREAMING LOGIC: Send if buffer is decent or has a newline
                                # For WhatsApp, we buffer a bit to avoid notification spam
                                buffer_threshold = 150 if source == "whatsapp" else 50
                                if "\n" in current_buffer or len(current_buffer) >= buffer_threshold:
                                    logger.info(f"[BROKER TRACE] Streaming chunk to {session_id} ({len(current_buffer)} chars)")
                                    await send_fn(current_buffer.strip())
                                    current_buffer = ""
                            
                    elif event["type"] == "tool_call":
                        # We intentionally DO NOT fire status updates for individual tools
                        # to prevent massive spam on the user's phone.
                        pass
                            
            except Exception as inner_e:
                logger.error(f"Error during agent stream for {session_id}: {inner_e}", exc_info=True)
                # Surface the error to the user so they aren't left with just a typing indicator
                error_msg = f"⚠️ Goku ran into an issue mid-response. Please try again. (Detail: {str(inner_e)[:120]})"  # type: ignore[index]
                try:
                    await send_fn(error_msg)
                except Exception:
                    pass

            # 3. Final Response (Residual buffer)
            if current_buffer.strip():
                logger.info(f"[BROKER TRACE] Sending residual buffer to {session_id}")
                await send_fn(current_buffer.strip())
            
            if not response_text:
                logger.warning(f"[BROKER TRACE] Agent returned empty response for {session_id}")

        except Exception as e:
            logger.error(f"Fatal error running agent for {session_id}: {e}", exc_info=True)
            await send_fn(f"⚠️ Sorry, Goku hit an error: {str(e)}")
        finally:
            if status_fn:
                try:
                    await status_fn("paused")
                except:
                    pass
            self._busy_sessions.remove(session_id)
            logger.debug(f"[BROKER TRACE] Session {session_id} marked as free")


channel_broker = ChannelBroker()
