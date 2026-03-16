import logging
import os
import asyncio
import threading
from typing import Optional, Dict, Any, List
from neonize.client import NewClient # type: ignore
from neonize.events import MessageEv, ConnectedEv # type: ignore
from neonize.utils.enum import ChatPresence, ChatPresenceMedia, ReceiptType # type: ignore
from .channel_manager import channel_broker # type: ignore
from .config_manager import config_manager # type: ignore
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import ReactionMessage, Message # type: ignore
from neonize.proto.waCommon.WACommon_pb2 import MessageKey # type: ignore
import time

logger = logging.getLogger("WhatsAppBot")

class WhatsAppBot:
    """WhatsApp Bot using Neonize (QR-code based) as the primary provider."""
    
    def __init__(self):
        self.client: NewClient | None = None
        self.is_connected = False
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        # Path to store credentials (relative to working dir)
        self.db_path = os.path.join("server", "whatsapp_session.db")
        self.bot_lid_user = ""
        self._group_info_cache: Dict[str, str] = {} # {jid: name}

    def _qr_callback(self, client: NewClient, qr: bytes):
        """Called when a new QR code is generated. Renders inline + saves to disk."""
        logger.info("New WhatsApp QR code generated.")
        qr_str = qr.decode() if isinstance(qr, bytes) else qr
        
        # Save raw QR data for CLI rendering
        txt_path = os.path.join("uploads", "whatsapp_qr.txt")
        try:
            with open(txt_path, "w") as f:
                f.write(qr_str)
        except Exception as e:
            logger.warning(f"Could not save QR text: {e}")

        # Save PNG image as well
        try:
            import segno # type: ignore
            qr_path = os.path.join("uploads", "whatsapp_qr.png")
            qrcode = segno.make(qr_str)
            qrcode.save(qr_path, scale=10)
            # Render directly in terminal (used by CLI)
            qrcode.terminal(compact=True)
            logger.info(f"QR image saved to {qr_path}.")
        except Exception as e:
            logger.error(f"Failed to generate/display QR image: {e}")

    def _check_connectivity(self) -> bool:
        """Check if we can resolve web.whatsapp.com to prevent Go panic."""
        import socket
        try:
            socket.gethostbyname("web.whatsapp.com")
            return True
        except socket.gaierror:
            logger.error("🛑 WhatsApp connectivity check failed: web.whatsapp.com is unreachable (DNS error).")
            return False
        except Exception as e:
            logger.error(f"⚠️ Connectivity check error: {e}")
            return False

    def start(self, main_loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start the WhatsApp client (blocking). Call in a thread."""
        self.main_loop = main_loop
        
        # 0. Pre-flight check
        if not self._check_connectivity():
            logger.warning("📴 Skipping WhatsApp startup due to network/DNS issues.")
            self.is_connected = False
            return

        try:
            os.makedirs("uploads", exist_ok=True)
            self.client = NewClient(self.db_path)
            client = self.client

            # Register the QR callback using the correct Event API
            client.event.qr(self._qr_callback)

            # Register interface for proactive messaging
            async def send_wa_interface(session_id: str, text: str):
                chat_jid = session_id.replace("wa_", "")
                await self.send_message_direct(chat_jid, text)

            async def list_wa_groups() -> List[Dict[str, str]]:
                if not self.client: return []
                try:
                    # Neonize call
                    groups = self.client.get_joined_groups()
                    results = []
                    for g in groups:
                        jid_str = f"{g.JID.User}@{g.JID.Server}"
                        results.append({
                            "jid": jid_str,
                            "name": g.GroupName or "Unknown Group",
                            "session_id": f"wa_{jid_str}"
                        })
                    return results
                except Exception as e:
                    logger.error(f"Failed to list WhatsApp groups: {e}")
                    return []

            channel_broker.register_interface("whatsapp", send_wa_interface, list_wa_groups)

            # Register connected event
            @client.event(ConnectedEv)
            def on_connected(c: NewClient, e: ConnectedEv): # type: ignore
                logger.info(f"WhatsApp ConnectedEv received: {e}")
                self.is_connected = True
                config_manager.set_key("WHATSAPP_LINKED", "true")
                logger.info("WhatsApp connected and status persisted.")

            from neonize.events import PairStatusEv # type: ignore
            @client.event(PairStatusEv)
            def on_pair_status(c: NewClient, e: PairStatusEv): # type: ignore
                logger.info(f"WhatsApp PairStatusEv received: {e}")
                # If we get a pair status success, we are linked
                self.is_connected = True
                config_manager.set_key("WHATSAPP_LINKED", "true")

            import re
            
            # Robust JID parsing inspired by OpenClaw
            USER_JID_RE = re.compile(r"^(\d+)(?::\d+)?@s\.whatsapp\.net$", re.I)
            LID_RE = re.compile(r"^(\d+)@lid$", re.I)

            def safe_get_jid(obj) -> str:
                """Extremely defensive JID to string conversion."""
                if obj is None: return ""
                if isinstance(obj, str): return obj
                try:
                    # Neonize JID objects usually have User and Server attributes
                    # Accessing them directly is safer than str() which triggers proto field lookups
                    user = getattr(obj, "User", "")
                    server = getattr(obj, "Server", "")
                    if user and server:
                        return f"{user}@{server}"
                    return str(obj)
                except Exception as e:
                    logger.debug(f"JID stringify fallback for {type(obj)}: {e}")
                    return str(obj)

            def get_phone_from_jid(jid_obj) -> str:
                jid = safe_get_jid(jid_obj)
                # Primary match: s.whatsapp.net
                m = USER_JID_RE.match(jid)
                if m:
                    return m.group(1)
                
                # LID match: return digits as a fallback phone
                m_lid = LID_RE.match(jid)
                if m_lid:
                    lid_user = m_lid.group(1)
                    logger.debug(f"[TRACE] Detected LID identifier: {lid_user}")
                    return lid_user

                return jid.split("@")[0].split(":")[0]

            # Register message handler
            @client.event(MessageEv)
            def on_message_sync(c: NewClient, message: MessageEv): # type: ignore
                try:
                    logger.debug("WhatsAppBot v2.5 (LID-aware, Improved Mention)")
                    src = message.Info.MessageSource
                    raw_chat = src.Chat
                    chat_jid = safe_get_jid(raw_chat)
                    is_group = "@g.us" in chat_jid
                    is_from_me = src.IsFromMe
                    
                    logger.debug(f"[TRACE] Incoming message: chat_jid={chat_jid}, is_group={is_group}, is_from_me={is_from_me}")
                    
                    # 0. Bot Identification
                    bot_info = None
                    try:
                        bot_info = c.get_me()
                    except Exception as e:
                        logger.debug(f"[TRACE] Could not get_me(): {e}")
                    
                    bot_jid = safe_get_jid(bot_info.JID) if bot_info else ""
                    bot_phone = get_phone_from_jid(bot_jid) if bot_jid else ""
                    bot_lid = safe_get_jid(getattr(bot_info, "LID", None)) if bot_info else ""
                    
                    # Store for persistent mention check
                    if bot_lid:
                        lid_user = bot_lid.split("@")[0]
                        if not self.bot_lid_user or self.bot_lid_user != lid_user:
                            self.bot_lid_user = lid_user
                            logger.info(f"Identified Bot LID: {self.bot_lid_user}")

                    # RELAXED SELF-CHAT: If it's from us and not a group, it's a self-chat (DM to self)
                    # We don't compare JIDs because they might be LID vs s.whatsapp.net
                    is_self_chat = is_from_me and not is_group
                    
                    logger.debug(f"[TRACE] Bot info: bot_jid={bot_jid}, bot_phone={bot_phone}, bot_lid_user={self.bot_lid_user}, is_self_chat={is_self_chat}")
                    
                    # Capture own LID if we see ourselves sending a message
                    if is_from_me:
                        lid_match = LID_RE.match(chat_jid)
                        if lid_match:
                            self.bot_lid_user = lid_match.group(1)
                            logger.info(f"Learned Bot LID: {self.bot_lid_user}")
                    
                    # Ignore normal outgoing messages (sent by bot to others)
                    if is_from_me and not is_self_chat:
                        logger.debug("[TRACE] Ignoring outgoing message (sent by us to someone else)")
                        return
                    
                    # 1. Configuration & Policy
                    dm_policy = config_manager.get_key("WHATSAPP_DM_POLICY", "allowlist").lower()
                    group_policy = config_manager.get_key("WHATSAPP_GROUP_POLICY", "mentions").lower()
                    allow_raw = config_manager.get_key("WHATSAPP_ALLOW_FROM", "")
                    owner_raw = config_manager.get_key("GOKU_OWNER_NUMBER", "")
                    
                    def normalize_digits(p: str):
                        return "".join(filter(str.isdigit, p))
                        
                    owner_ph = normalize_digits(owner_raw)
                    allow_list = [normalize_digits(x) for x in allow_raw.split(",") if x.strip()]

                    # 2. LID resolution (Privacy identifiers)
                    sender_jid = chat_jid
                    if is_group:
                        sender_raw = src.Sender
                        sender_jid = safe_get_jid(sender_raw)

                    # Extract sender phone
                    sender_ph = get_phone_from_jid(sender_jid)

                    # Aggressive LID resolution (check multiple fields)
                    if "@lid" in sender_jid:
                        # Try SenderPn
                        if hasattr(src, "SenderPn") and src.SenderPn.User:
                            sender_ph = src.SenderPn.User
                            logger.debug(f"[TRACE] Resolved LID to Phone (SenderPn): {sender_ph}")
                        else:
                            # Try SenderAlt
                            if hasattr(src, "SenderAlt") and src.SenderAlt:
                                alts = src.SenderAlt if isinstance(src.SenderAlt, (list, tuple)) else [src.SenderAlt]
                                for alt in alts:
                                    res_ph = get_phone_from_jid(alt)
                                    if res_ph:
                                        sender_ph = res_ph
                                        logger.debug(f"[TRACE] Resolved LID to Phone (SenderAlt): {sender_ph}")
                                        break
                            
                            # Final fallback: RecipientAlt
                            if not sender_ph or len(sender_ph) < 5:
                                if hasattr(src, "RecipientAlt") and src.RecipientAlt:
                                    alts = src.RecipientAlt if isinstance(src.RecipientAlt, (list, tuple)) else [src.RecipientAlt]
                                    for alt in alts:
                                        res_ph = get_phone_from_jid(alt)
                                        if res_ph:
                                            sender_ph = res_ph
                                            logger.debug(f"[TRACE] Resolved LID to Phone (RecipientAlt): {sender_ph}")
                                            break

                    logger.debug(f"Source JID: {sender_jid}, Resolved Phone: {sender_ph}")

                    # 3. Policy Check
                    # Owner always has access. If is_self_chat is True, it's the owner's account.
                    is_owner = is_self_chat or (owner_ph and sender_ph == owner_ph)
                    
                    if not is_owner:
                        if not is_group:
                            if dm_policy == "disabled":
                                logger.info("Policy: DM disabled")
                                return
                            if dm_policy == "allowlist":
                                if sender_ph not in allow_list and "*" not in allow_raw:
                                    # Exact match check
                                    matched_any = False
                                    for allowed in allow_list:
                                        if allowed == sender_ph:
                                            matched_any = True
                                            break
                                    if not matched_any:
                                        logger.info(f"Policy: Blocking DM from +{sender_ph} (not in allowlist)")
                                        return
                        else:
                            if group_policy == "disabled":
                                logger.info("Policy: Group disabled")
                                return
                            if group_policy == "allowlist":
                                if sender_ph not in allow_list and "*" not in allow_raw:
                                    logger.info(f"Policy: Blocking group sender +{sender_ph}")
                                    return
                    
                    # 4. Content Extraction
                    msg = message.Message
                    text = ""
                    if hasattr(msg, "conversation") and msg.conversation:
                        text = msg.conversation
                    elif hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage:
                        text = msg.extendedTextMessage.text
                    elif hasattr(msg, "imageMessage") and msg.imageMessage:
                        text = msg.imageMessage.caption
                    elif hasattr(msg, "videoMessage") and msg.videoMessage:
                        text = msg.videoMessage.caption
                    elif hasattr(msg, "documentMessage") and msg.documentMessage:
                        text = msg.documentMessage.caption
                    
                    logger.debug(f"[TRACE] Extracted text: {text[:50]}...")

                    if not text:
                        logger.debug("[TRACE] No text content found, ignoring.")
                        return

                    # Mentions
                    if is_group and group_policy == "mentions":
                        # 1. Proto-level mentionedJid check (Native tagging)
                        proto_mentioned = False
                        ctx = None
                        if hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage.contextInfo:
                            ctx = msg.extendedTextMessage.contextInfo
                        elif hasattr(msg, "imageMessage") and msg.imageMessage.contextInfo:
                            ctx = msg.imageMessage.contextInfo
                        elif hasattr(msg, "videoMessage") and msg.videoMessage.contextInfo:
                            ctx = msg.videoMessage.contextInfo
                        elif hasattr(msg, "documentMessage") and msg.documentMessage.contextInfo:
                            ctx = msg.documentMessage.contextInfo

                        if ctx and hasattr(ctx, "mentionedJid") and ctx.mentionedJid:
                            for mjid in ctx.mentionedJid:
                                # Check if tagged JID matches our Phone (digits) or LID (digits)
                                if (bot_phone and bot_phone in mjid) or (self.bot_lid_user and self.bot_lid_user in mjid):
                                    proto_mentioned = True
                                    break
                        
                        # 2. Text-based fallback (Look for name or ID digits)
                        bot_jid_digits = normalize_digits(bot_jid)
                        
                        text_mentioned = (
                            "goku" in text.lower() or 
                            "@all" in text.lower() or
                            (bot_phone and bot_phone in text) or
                            (bot_jid_digits and bot_jid_digits in text) or
                            (self.bot_lid_user and self.bot_lid_user in text)
                        )
                        
                        mentioned = proto_mentioned or text_mentioned
                        logger.debug(f"Group mention check (v3): proto={proto_mentioned}, text={text_mentioned}, final={mentioned}")
                        if not mentioned:
                            return

                    logger.info(f"Accepted WhatsApp message from +{sender_ph} in {chat_jid}")
                    # Mark the message as read (blue ticks)
                    try:
                        c.mark_read(
                            message.Info.ID,
                            chat=raw_chat,
                            sender=message.Info.MessageSource.Sender if is_group else raw_chat,
                            receipt=ReceiptType.READ,
                        )
                    except Exception as e:
                        logger.warning(f"[TRACE] Failed to mark message {message.Info.ID} as read: {e}")
                    try:
                        # Send "typing..." indicator immediately
                        c.send_chat_presence(raw_chat, ChatPresence.CHAT_PRESENCE_COMPOSING, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
                    except:
                        pass
                    session_id = f"wa_{chat_jid}"
                    
                    # Sender Identification: Always enrich the message with sender context.
                    # This allows personas to identify VIPs (e.g., the CEO's number) from their system prompt.
                    if is_group:
                        # Fetch group name
                        group_name = self._group_info_cache.get(chat_jid, "")
                        if not group_name:
                            try:
                                g_info = c.get_group_info(raw_chat)
                                if g_info and g_info.GroupName:
                                    group_name = g_info.GroupName
                                    self._group_info_cache[chat_jid] = group_name
                            except Exception as e:
                                logger.debug(f"[TRACE] Could not fetch group info for {chat_jid}: {e}")
                        
                        group_prefix = f"[GROUP: {group_name}] " if group_name else ""
                        sender_name = getattr(message.Info, "PushName", "") or sender_ph or "Unknown"
                        text = f"{group_prefix}[FROM: {sender_name} (+{sender_ph})]: {text}"
                    else:
                        # For DMs, the 'from' is implicit but we still surface the phone number
                        # so personas can match it against VIP numbers in their instructions.
                        sender_name = getattr(message.Info, "PushName", "") or "User"
                        if sender_ph:
                            text = f"[FROM: {sender_name} (+{sender_ph})]: {text}"

                    # 5. Delegate to Main Event Loop (Thread-Safe)
                    # We must run this on the main loop so timers/tasks in channel_broker survive
                    async def async_delegate():
                        logger.debug(f"[TRACE] async_delegate started for {session_id}")
                        try:
                            async def send_wa_message(resp_text: str):
                                logger.debug(f"[TRACE] Attempting to send WA response to {chat_jid}")
                                try:
                                    from server.whatsapp_formatter import format_for_whatsapp # type: ignore
                                    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message as WAMessage # type: ignore
                                    
                                    resp_text = format_for_whatsapp(resp_text)
                                    # Send as an explicit conversation message proto to avoid sanitization
                                    c.send_message(raw_chat, WAMessage(conversation=resp_text))
                                    logger.info(f"[TRACE] Successfully sent WA response to {chat_jid}")
                                except Exception as e:
                                    logger.error(f"WhatsApp send failed: {e}")

                            async def status_update(status: str):
                                try:
                                    # Any non-empty status should keep the typing indicator active
                                    if status and status != "paused":
                                        c.send_chat_presence(raw_chat, ChatPresence.CHAT_PRESENCE_COMPOSING, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
                                    else:
                                        c.send_chat_presence(raw_chat, ChatPresence.CHAT_PRESENCE_PAUSED, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
                                except:
                                    pass

                            async def react_wa(emoji: str):
                                logger.debug(f"[TRACE] Attempting to send reaction {emoji} to {chat_jid}")
                                try:
                                    # Build the message key for the target message
                                    key = MessageKey(
                                        remoteJID=chat_jid,
                                        fromMe=False,
                                        ID=message.Info.ID,
                                        participant=safe_get_jid(message.Info.MessageSource.Sender) if is_group else ""
                                    )
                                    
                                    reaction = ReactionMessage(
                                        key=key,
                                        text=emoji,
                                        senderTimestampMS=int(time.time() * 1000)
                                    )
                                    
                                    msg_obj = Message(reactionMessage=reaction)
                                    c.send_message(raw_chat, msg_obj)
                                    logger.info(f"[TRACE] Successfully reacted {emoji} to {chat_jid}")
                                except Exception as e:
                                    logger.error(f"WhatsApp reaction failed: {e}")

                            await channel_broker.handle_incoming_message(
                                session_id=session_id,
                                content=text,
                                source="whatsapp",
                                send_message_fn=send_wa_message,
                                status_update_fn=status_update,
                                react_fn=react_wa,
                                is_group=is_group
                            )
                            logger.debug(f"[TRACE] channel_broker.handle_incoming_message completed for {session_id}")
                        except Exception as e:
                            logger.error(f"WhatsApp delegate handler failed: {e}", exc_info=True)

                    target_loop = self.main_loop
                    
                    # Log thread info for debugging
                    curr_thread = threading.current_thread().name
                    
                    # Check if the stored loop is usable
                    loop_usable = False
                    if target_loop:
                        try:
                            if not target_loop.is_closed():
                                loop_usable = True
                        except Exception:
                            pass

                    if loop_usable:
                        logger.debug(f"[TRACE] Delegating to main_loop from thread {curr_thread}")
                        asyncio.run_coroutine_threadsafe(async_delegate(), target_loop) # type: ignore
                    else:
                        logger.warning(f"[TRACE] main_loop is Null or CLOSED in thread {curr_thread}. Attempting recovery...")
                        try:
                            # Try to find any other running loop (last resort before creating new)
                            current_loop = None
                            try:
                                current_loop = asyncio.get_running_loop()
                            except RuntimeError:
                                # Not in a running loop thread, this is expected for the bot thread
                                pass
                            
                            if current_loop and not current_loop.is_closed():
                                logger.info(f"[TRACE] Found fallback running loop in thread {curr_thread}")
                                asyncio.run_coroutine_threadsafe(async_delegate(), current_loop)
                            else:
                                # Start a one-off loop for this message if everything else fails
                                # This is slow but prevents the "typing" hang
                                logger.warning(f"[TRACE] No usable loop found. Spawning temporary responder loop.")
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                loop.run_until_complete(async_delegate())
                                loop.close()
                        except Exception as e:
                            logger.error(f"❌ Failed all loop recovery attempts: {e}")

                except Exception as e:
                    logger.error(f"Error handling WhatsApp message: {e}", exc_info=True)

            async def heartbeat():
                while True:
                    try:
                        await asyncio.sleep(60)
                        logger.debug(f"[HEARTBEAT] WhatsApp Bot is alive. Connected: {self.is_connected}")
                    except asyncio.CancelledError:
                        break
                    except:
                        pass

            if self.main_loop is not None:
                from typing import cast
                ml = cast(asyncio.AbstractEventLoop, self.main_loop)
                asyncio.run_coroutine_threadsafe(heartbeat(), ml)

            logger.info("Starting WhatsApp client (blocking call)...")
            client.connect()

        except Exception as e:
            logger.error(f"Failed to start WhatsApp: {e}")

    async def send_message_direct(self, chat_jid: str, text: str):
        """Send a message directly to a JID without an incoming message context."""
        if not self.client or not self.is_connected:
            logger.error(f"Cannot send message to {chat_jid}: WhatsApp not connected.")
            return
        
        try:
            from server.whatsapp_formatter import format_for_whatsapp # type: ignore
            from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message as WAMessage # type: ignore
            from neonize.utils import JID # type: ignore

            formatted_text = format_for_whatsapp(text)
            # Ensure JID is an object if needed, neonize.client.send_message usually takes JID or string
            # We'll use the raw string if it's already a full JID
            self.client.send_message(chat_jid, WAMessage(conversation=formatted_text))
            logger.info(f"Proactive WA message sent to {chat_jid}")
        except Exception as e:
            logger.error(f"Failed to send direct WhatsApp message: {e}")

    def logout(self):
        """Disconnect and delete the session database."""
        try:
            if self.client:
                # whatsmeow doesn't have a simple 'logout' but we can disconnect
                # and delete the session.db to force a fresh QR next time.
                self.client.disconnect()
            
            self.is_connected = False
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            
            # Clean up QR files as well
            for f in ["whatsapp_qr.png", "whatsapp_qr.txt"]:
                path = os.path.join("uploads", f)
                if os.path.exists(path):
                    os.remove(path)
                    
            config_manager.set_key("WHATSAPP_LINKED", "false")
            logger.info("WhatsApp session reset successfully.")
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False

whatsapp_bot = WhatsAppBot()

async def run_whatsapp_bot(main_loop: Optional[asyncio.AbstractEventLoop] = None):
    """Helper to run the blocking WhatsApp client in a thread."""
    await asyncio.to_thread(whatsapp_bot.start, main_loop) # type: ignore
