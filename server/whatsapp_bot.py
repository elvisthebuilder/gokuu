import logging
import os
import asyncio
import threading
import time
from typing import Optional, Dict, Any, List
from neonize.client import NewClient # type: ignore
from neonize.events import MessageEv, ConnectedEv # type: ignore
from neonize.utils.enum import ChatPresence, ChatPresenceMedia, ReceiptType # type: ignore
from .channel_manager import channel_broker # type: ignore
from .config_manager import config_manager # type: ignore
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import ReactionMessage, Message, AudioMessage # type: ignore
from neonize.proto.waCommon.WACommon_pb2 import MessageKey # type: ignore
from neonize.utils.jid import JID # type: ignore
from .personality_manager import personality_manager # type: ignore
from .memory import memory, GOKU_DEFAULT_PERSONA # type: ignore

logger = logging.getLogger("WhatsAppBot")

class WhatsAppBot:
    """WhatsApp Bot using Neonize (QR-code based) as the primary provider."""
    
    def __init__(self):
        self.client: NewClient | None = None
        self.is_connected = False
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        self.db_path = os.path.join("server", "whatsapp_session.db")
        self.bot_lid_user = ""
        self._group_info_cache: Dict[str, Any] = {} # {jid: GroupInfo}
        self._last_group_refresh: Dict[str, float] = {} # {jid: timestamp}

    def _qr_callback(self, client: NewClient, qr: bytes):
        """Called when a new QR code is generated."""
        logger.info("New WhatsApp QR code generated.")
        qr_str = qr.decode() if isinstance(qr, bytes) else qr
        txt_path = os.path.join("uploads", "whatsapp_qr.txt")
        try:
            with open(txt_path, "w") as f:
                f.write(qr_str)
        except Exception as e:
            logger.warning(f"Could not save QR text: {e}")

        try:
            import segno # type: ignore
            qr_path = os.path.join("uploads", "whatsapp_qr.png")
            qrcode = segno.make(qr_str)
            qrcode.save(qr_path, scale=10)
            qrcode.terminal(compact=True)
            logger.info(f"QR image saved to {qr_path}.")
        except Exception as e:
            logger.error(f"Failed to generate QR image: {e}")

    def _check_connectivity(self) -> bool:
        """DNS check for WhatsApp."""
        import socket
        try:
            socket.gethostbyname("web.whatsapp.com")
            return True
        except:
            return False

    def start(self, main_loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start the WhatsApp client."""
        self.main_loop = main_loop
        if not self._check_connectivity():
            logger.warning("WhatsApp connectivity issues, skipping.")
            self.is_connected = False
            return

        try:
            os.makedirs("uploads", exist_ok=True)
            self.client = NewClient(self.db_path)
            client = self.client
            client.event.qr(self._qr_callback)

            async def send_wa_interface(session_id: str, text: str):
                chat_jid = session_id.replace("wa_", "")
                await self.send_message_direct(chat_jid, text)

            async def list_wa_groups() -> List[Dict[str, str]]:
                if not self.client: return []
                try:
                    groups = self.client.get_joined_groups()
                    return [{"jid": f"{g.JID.User}@{g.JID.Server}", "name": g.GroupName or "Unknown Group", "session_id": f"wa_{g.JID.User}@{g.JID.Server}"} for g in groups]
                except Exception as e:
                    logger.error(f"Groups error: {e}")
                    return []

            async def get_wa_chat_info(session_id: str) -> Dict[str, Any]:
                jid_str = session_id.replace("wa_", "")
                if not self.client: return {"status": "error", "message": "Client not initialized"}
                try:
                    user, server = jid_str.split("@", 1)
                    target_jid = JID(User=user, Server=server)
                    if server == "g.us":
                        info = self.client.get_group_info(target_jid)
                        if info:
                            return {
                                "status": "success",
                                "name": info.GroupName or "Unknown Group",
                                "participants": [{"jid": f"{p.JID.User}@{p.JID.Server}", "role": "admin" if p.IsAdmin else "member"} for p in info.Participants],
                                "description": info.GroupDescription or ""
                            }
                    else:
                        info = self.client.get_user_info([target_jid])
                        # user_info returns a list or dict depending on version
                        return {"status": "success", "jid": jid_str, "info": str(info)}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
                return {"status": "error", "message": "Chat not found"}

            channel_broker.register_interface("whatsapp", send_wa_interface, list_wa_groups, get_wa_chat_info)

            @client.event(ConnectedEv)
            def on_connected(c: NewClient, e: ConnectedEv): # type: ignore
                self.is_connected = True
                config_manager.set_key("WHATSAPP_LINKED", "true")
                logger.info("WhatsApp connected.")

            from neonize.events import PairStatusEv # type: ignore
            @client.event(PairStatusEv)
            def on_pair_status(c: NewClient, e: PairStatusEv): # type: ignore
                self.is_connected = True
                config_manager.set_key("WHATSAPP_LINKED", "true")

            import re
            USER_JID_RE = re.compile(r"^(\d+)(?::\d+)?@s\.whatsapp\.net$", re.I)
            LID_RE = re.compile(r"^(\d+)@lid$", re.I)

            def safe_get_jid(obj) -> str:
                if obj is None: return ""
                if isinstance(obj, str): return obj
                try:
                    user, server = getattr(obj, "User", ""), getattr(obj, "Server", "")
                    if user and server: return f"{user}@{server}"
                    return str(obj)
                except: return str(obj)

            def get_phone_from_jid(jid_obj) -> str:
                jid = safe_get_jid(jid_obj)
                m = USER_JID_RE.match(jid) or LID_RE.match(jid)
                return m.group(1) if m else jid.split("@")[0].split(":")[0]

            @client.event(MessageEv)
            def on_message_sync(c: NewClient, message: MessageEv): # type: ignore
                try:
                    src = message.Info.MessageSource
                    raw_chat = src.Chat
                    chat_jid = safe_get_jid(raw_chat)
                    is_group = "@g.us" in chat_jid
                    is_from_me = src.IsFromMe
                    
                    bot_info = None
                    try: bot_info = c.get_me()
                    except: pass
                    bot_jid = safe_get_jid(bot_info.JID) if bot_info else ""
                    bot_phone = get_phone_from_jid(bot_jid) if bot_jid else ""
                    bot_lid = safe_get_jid(getattr(bot_info, "LID", None)) if bot_info else ""
                    if bot_lid:
                        lu = bot_lid.split("@")[0]
                        if not self.bot_lid_user or self.bot_lid_user != lu: self.bot_lid_user = lu

                    is_self_chat = is_from_me and not is_group
                    if is_from_me and not is_self_chat: return
                    
                    dm_policy = config_manager.get_key("WHATSAPP_DM_POLICY", "allowlist").lower()
                    group_policy = config_manager.get_key("WHATSAPP_GROUP_POLICY", "mentions").lower()
                    allow_raw = config_manager.get_key("WHATSAPP_ALLOW_FROM", "")
                    owner_raw = config_manager.get_key("GOKU_OWNER_NUMBER", "")
                    def norm(p: str): return "".join(filter(str.isdigit, p))
                    owner_ph = norm(owner_raw)
                    allow_list = [norm(x) for x in allow_raw.split(",") if x.strip()]

                    sender_jid = safe_get_jid(src.Sender) if is_group else chat_jid
                    sender_ph = get_phone_from_jid(sender_jid)
                    sender_name = getattr(message.Info, "Pushname", "") or "Unknown"
                    sender_role = "Member"
                    
                    if is_group:
                        # Try to resolve group role (Admin/Member)
                        now = time.time()
                        if chat_jid not in self._group_info_cache or now - self._last_group_refresh.get(chat_jid, 0) > 300:
                            try:
                                g_info = c.get_group_info(raw_chat)
                                if g_info:
                                    self._group_info_cache[chat_jid] = g_info
                                    self._last_group_refresh[chat_jid] = now
                            except: pass
                        
                        g_info = self._group_info_cache.get(chat_jid)
                        if g_info and hasattr(g_info, "Participants"):
                            for p in g_info.Participants:
                                p_jid = f"{p.JID.User}@{p.JID.Server}"
                                if p_jid == sender_jid or p_jid == sender_ph + "@s.whatsapp.net":
                                    if getattr(p, "IsAdmin", False) or getattr(p, "IsSuperAdmin", False):
                                        sender_role = "Admin"
                                    break

                    if "@lid" in sender_jid:
                        if hasattr(src, "SenderPn") and src.SenderPn.User: sender_ph = src.SenderPn.User
                        elif hasattr(src, "SenderAlt") and src.SenderAlt:
                            alts = src.SenderAlt if isinstance(src.SenderAlt, (list, tuple)) else [src.SenderAlt]
                            for alt in alts:
                                if res := get_phone_from_jid(alt): sender_ph = res; break

                    is_owner = is_self_chat or (owner_ph and sender_ph == owner_ph)
                    if not is_owner:
                        if not is_group:
                            if dm_policy == "disabled" or (dm_policy == "allowlist" and sender_ph not in allow_list and "*" not in allow_raw): return
                        else:
                            if group_policy == "disabled" or (group_policy == "allowlist" and sender_ph not in allow_list and "*" not in allow_raw): return
                    
                    msg = message.Message
                    
                    # Unwrap ephemeral and view_once messages using proper Protobuf HasField checks
                    if msg.HasField("ephemeralMessage") and msg.ephemeralMessage.message:
                        msg = msg.ephemeralMessage.message
                    elif msg.HasField("viewOnceMessage") and msg.viewOnceMessage.message:
                        msg = msg.viewOnceMessage.message
                    elif msg.HasField("viewOnceMessageV2") and msg.viewOnceMessageV2.message:
                        msg = msg.viewOnceMessageV2.message
                    elif msg.HasField("documentWithCaptionMessage") and msg.documentWithCaptionMessage.message:
                        msg = msg.documentWithCaptionMessage.message
                    elif msg.HasField("viewOnceMessageV2Extension") and msg.viewOnceMessageV2Extension.message:
                        msg = msg.viewOnceMessageV2Extension.message

                    text, attachment_path, is_voice, m_type, original_filename = "", None, False, None, ""
                    if msg.conversation: text = msg.conversation
                    elif msg.HasField("extendedTextMessage"): text = msg.extendedTextMessage.text
                    elif msg.HasField("imageMessage"): text, m_type = msg.imageMessage.caption, "image"
                    elif msg.HasField("videoMessage"): text, m_type = msg.videoMessage.caption, "video"
                    elif msg.HasField("documentMessage"):
                        text, m_type = msg.documentMessage.caption, "document"
                        original_filename = getattr(msg.documentMessage, "fileName", "")
                        # Forwarded voice notes and audio often arrive as Documents
                        if original_filename:
                            ext = original_filename.lower().split(".")[-1]
                            if ext in ["ogg", "mp3", "m4a", "wav", "aac", "opus"]:
                                m_type, is_voice = "audio", True
                        elif hasattr(msg.documentMessage, "mimetype"):
                            if "audio" in msg.documentMessage.mimetype.lower():
                                m_type, is_voice = "audio", True
                    elif msg.HasField("audioMessage"): m_type, is_voice = "audio", True
                    elif msg.HasField("stickerMessage"): m_type = "sticker"

                    if m_type:
                        try:
                            logger.info(f"Downloading {m_type}...")
                            b = c.download_any(msg)
                            if b:
                                ts = time.strftime("%Y%m%d_%H%M%S")
                                ext = {"image": ".jpg", "video": ".mp4", "audio": ".ogg", "document": ".bin", "sticker": ".webp"}.get(m_type, ".bin")
                                
                                # Improve extension for documents
                                if m_type == "document":
                                    if original_filename and "." in original_filename:
                                        ext = os.path.splitext(original_filename)[1]
                                    elif hasattr(msg.documentMessage, "mimetype"):
                                        mt = msg.documentMessage.mimetype
                                        if "/" in mt: ext = "." + mt.split("/")[-1]
                                
                                base_name = f"wa_{m_type}_{ts}"
                                if original_filename:
                                    # Clean filename for filesystem
                                    safe_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in original_filename])
                                    base_name = f"wa_{ts}_{safe_name}"
                                    ext = "" # extension is already in safe_name
                                    
                                attachment_path = os.path.join("uploads", f"{base_name}{ext}")
                                os.makedirs("uploads", exist_ok=True)
                                with open(attachment_path, "wb") as f: f.write(b)
                        except Exception as e: logger.error(f"Download error: {e}")

                    session_id = f"wa_{chat_jid}"
                    mentioned = not is_group or is_self_chat
                    p_text = ""
                    lu = self.bot_lid_user
                    
                    async def async_delegate():
                        nonlocal text, mentioned, p_text
                        try:
                            # 1. Transcribe if voice
                            if is_voice:
                                if attachment_path:
                                    from .speech_service import transcribe_audio # type: ignore
                                    transcript = await transcribe_audio(attachment_path)
                                    if transcript:
                                        text = ("[Voice Note Transcript]: " + transcript).strip()
                                    else:
                                        logger.warning(f"STT transcription failed for {attachment_path}. Notifying user.")
                                        try:
                                            c.send_message(raw_chat, Message(conversation="🎙️ I received your voice note, but I couldn't transcribe it. Make sure an ELEVENLABS_API_KEY is set in your .env, then try again."))
                                        except Exception as se:
                                            logger.error(f"Failed to send STT error reply: {se}")
                                        return
                                else:
                                    # Audio download failed — attachment_path is None
                                    logger.warning("Voice note download failed (attachment_path is None). Notifying user.")
                                    try:
                                        c.send_message(raw_chat, Message(conversation="🎙️ I received your voice note, but failed to download it. Please try sending it again."))
                                    except Exception as se:
                                        logger.error(f"Failed to send download error reply: {se}")
                                    return
                            
                            # 2. Complete Mention Logic (now that we have transcript for voice)
                            if is_group and not mentioned:
                                proto_m, reply_m, ctx = False, False, None
                                if hasattr(msg, "extendedTextMessage") and msg.extendedTextMessage.contextInfo: ctx = msg.extendedTextMessage.contextInfo
                                elif hasattr(msg, "imageMessage") and msg.imageMessage.contextInfo: ctx = msg.imageMessage.contextInfo
                                elif hasattr(msg, "videoMessage") and msg.videoMessage.contextInfo: ctx = msg.videoMessage.contextInfo
                                elif hasattr(msg, "documentMessage") and msg.documentMessage.contextInfo: ctx = msg.documentMessage.contextInfo
                                
                                if ctx:
                                    if hasattr(ctx, "mentionedJid") and ctx.mentionedJid:
                                        for mjid in ctx.mentionedJid:
                                            if (bot_phone and bot_phone in mjid) or (lu and lu in mjid): proto_m = True; break
                                    if hasattr(ctx, "participant") and ctx.participant:
                                        q_jid = safe_get_jid(ctx.participant)
                                        if (bot_phone and bot_phone in q_jid) or (lu and lu in q_jid): reply_m = True
                                
                                text_l = (text or "").lower()
                                text_m = "goku" in text_l or "@all" in text_l or (bot_phone and bot_phone in text_l) or (lu and lu in text_l)
                                mentioned = proto_m or reply_m or text_m or (is_voice and is_owner)

                            # 3. Identity Awareness: Prefix message with sender details
                            if text:
                                p_text = f"[{sender_name} (@{sender_ph}) - {sender_role}]: {text}"
                            elif m_type:
                                p_text = f"[{sender_name} (@{sender_ph}) - {sender_role}] sent a <{m_type}>"
                            else:
                                return  # No content at all — ignore
                            if is_group:
                                p_text = f"[FROM: {sender_name}]: {p_text}"

                            # 4. If still not mentioned, just record to memory and exit
                            if not mentioned:
                                # Resolve the persona assigned to this group/chat for correct memory scoping
                                assigned_persona = None
                                try:
                                    mappings = personality_manager.get_all_mappings()
                                    assigned_persona = mappings.get(f"whatsapp:{chat_jid}") or mappings.get("whatsapp")
                                except: pass
                                
                                target_persona = assigned_persona or GOKU_DEFAULT_PERSONA
                                await memory.add_memory(
                                    text=f"[Passive Record] {text or f'<{m_type}>'}", 
                                    persona_name=target_persona, 
                                    metadata={"sender": sender_ph, "group": chat_jid, "passive": True}
                                )
                                logger.debug(f"Passive record for {target_persona} in {chat_jid}")
                                return

                            # 5. Handle the interaction
                            try: c.mark_read(message.Info.ID, chat=raw_chat, sender=message.Info.MessageSource.Sender if is_group else raw_chat, receipt=ReceiptType.READ)
                            except: pass
                            try: c.send_chat_presence(raw_chat, ChatPresence.CHAT_PRESENCE_COMPOSING, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
                            except: pass
                            
                            if not p_text and not attachment_path: return

                            async def send_wa(resp: str):
                                try:
                                    from server.whatsapp_formatter import format_for_whatsapp # type: ignore
                                    formatted = format_for_whatsapp(resp)
                                    if is_voice:
                                        from .speech_service import generate_speech # type: ignore
                                        ts = time.strftime("%Y%m%d_%H%M%S")
                                        rp = os.path.join("uploads", f"wa_r_{ts}.mp3")
                                        if await generate_speech(resp, rp):
                                            try:
                                                with open(rp, "rb") as af:
                                                    audio_bytes = af.read()
                                                file_len = len(audio_bytes)
                                                audio_msg = AudioMessage(ptt=True, mimetype="audio/mpeg", fileLength=file_len)
                                                c.send_message(raw_chat, Message(audioMessage=audio_msg))
                                            except Exception as ae:
                                                logger.error(f"WA audio reply error: {ae}; falling back to text.")
                                                c.send_message(raw_chat, Message(conversation=formatted))
                                            finally:
                                                try: os.remove(rp)
                                                except: pass
                                            return
                                    c.send_message(raw_chat, Message(conversation=formatted))
                                except Exception as e: logger.error(f"WA send error: {e}")

                            async def status_upd(s: str):
                                try:
                                    p = ChatPresence.CHAT_PRESENCE_COMPOSING if s and s != "paused" else ChatPresence.CHAT_PRESENCE_PAUSED
                                    c.send_chat_presence(raw_chat, p, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
                                except: pass

                            async def react_wa(e: str):
                                try:
                                    key = MessageKey(remoteJID=chat_jid, fromMe=False, ID=message.Info.ID, participant=sender_jid if is_group else "")
                                    c.send_message(raw_chat, Message(reactionMessage=ReactionMessage(key=key, text=e, senderTimestampMS=int(time.time()*1000))))
                                except: pass

                            await channel_broker.handle_incoming_message(session_id=session_id, content=p_text, source="whatsapp", send_message_fn=send_wa, status_update_fn=status_upd, react_fn=react_wa, is_voice=is_voice, attachment_path=attachment_path, is_group=is_group)
                        except Exception as ed: logger.error(f"WA delegate error: {ed}")

                    ml = self.main_loop
                    if ml is not None and not ml.is_closed():
                        asyncio.run_coroutine_threadsafe(async_delegate(), ml)
                except Exception as ex: logger.error(f"WA on_message_sync error: {ex}", exc_info=True)

            async def heartbeat():
                while True:
                    try:
                        await asyncio.sleep(60)
                        logger.debug(f"[HEARTBEAT] WhatsApp Bot alive. Connected: {self.is_connected}")
                    except: break

            ml = self.main_loop
            if ml is not None: asyncio.run_coroutine_threadsafe(heartbeat(), ml)
            logger.info("Starting WhatsApp client (blocking call)...")
            client.connect()

        except Exception as e:
            logger.error(f"Failed to start WhatsApp: {e}")

    async def send_message_direct(self, chat_jid: str, text: str):
        """Send direct proactive message with automatic mention support."""
        if not self.client or not self.is_connected: return
        try:
            import re
            from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message as WAMessage, ExtendedTextMessage, ContextInfo # type: ignore
            
            # Convert string JID to JID object for reliability (especially for groups)
            if "@" in chat_jid:
                user, server = chat_jid.split("@", 1)
                target_jid = JID(User=user, Server=server)
            else:
                target_jid = JID(User=chat_jid, Server="s.whatsapp.net")

            # Send typing status before message (Instant delivery, but feels natural)
            try:
                self.client.send_chat_presence(target_jid, ChatPresence.CHAT_PRESENCE_COMPOSING, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
            except: pass

            # Automatic Mentions: Parse @123456789 in the text
            mention_regex = r"@(\d{7,15})"
            mentions = re.findall(mention_regex, text)
            
            # ghost_mentions in neonize expects a comma-separated string of JIDs (or a single JID)
            # We'll provide it to ensure the protocol handles the mention properly.
            ghost_mentions_str = ",".join(list(set([m + "@s.whatsapp.net" for m in mentions]))) if mentions else None
            
            # Using ghost_mentions with a raw string is the most stable path in neonize
            res = self.client.send_message(target_jid, text, ghost_mentions=ghost_mentions_str)
            if res:
                logger.info(f"Direct WA message sent to {chat_jid} (Mentions: {len(mentions)}, Result: {res})")
            else:
                logger.warning(f"Direct WA message to {chat_jid} returned empty response (potential silent failure)")
        except Exception as e: logger.error(f"Direct send error to {chat_jid}: {e}", exc_info=True)

    def logout(self):
        """Disconnect and reset session."""
        try:
            if self.client: self.client.disconnect()
            self.is_connected = False
            if os.path.exists(self.db_path): os.remove(self.db_path)
            for f in ["whatsapp_qr.png", "whatsapp_qr.txt"]:
                p = os.path.join("uploads", f)
                if os.path.exists(p): os.remove(p)
            config_manager.set_key("WHATSAPP_LINKED", "false")
            logger.info("WhatsApp session reset.")
            return True
        except: return False

whatsapp_bot = WhatsAppBot()

async def run_whatsapp_bot(main_loop: Optional[asyncio.AbstractEventLoop] = None):
    """Run bot in thread."""
    await asyncio.to_thread(whatsapp_bot.start, main_loop) # type: ignore
