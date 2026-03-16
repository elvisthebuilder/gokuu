import logging
import asyncio
import os
from typing import cast, Any, Dict
import hashlib
import re
import json
from datetime import datetime, timedelta
from telegram import Update, constants # type: ignore
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters # type: ignore
from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore
from .agent import agent # type: ignore
from .config_manager import config_manager # type: ignore
from .telegram_formatter import format_for_telegram, strip_markdown, smart_chunk # type: ignore
from .speech_service import transcribe_audio, generate_speech # type: ignore

# Configure uploads directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Configure logging for bot
logger = logging.getLogger("TelegramBot")

# Global scheduler instance
scheduler = AsyncIOScheduler()

# Global application instance to prevent garbage collection
_application = None

# Message deduplication cache: {hash: expiry_timestamp}
_message_dedupe_cache: Dict[str, datetime] = {}
DEDUPE_WINDOW_SECONDS = 5

from server.channel_manager import channel_broker # type: ignore

def _describe_tool_action(tool_name: str, tool_args: dict) -> str:
    """Generate a human-readable status message from a tool call."""
    name = tool_name.lower()
    
    # Shell/bash commands — infer from the command content
    if "bash" in name or "shell" in name or "exec" in name:
        cmd = str(tool_args.get("command", tool_args.get("cmd", ""))).strip()
        if not cmd:
            return "⚙️ Running a command..."
        cmd_lower = cmd.lower()
        # File/directory operations
        if any(x in cmd_lower for x in ["ls", "find", "tree", "du"]):
            return "📂 Checking directory..."
        if any(x in cmd_lower for x in ["cat", "head", "tail", "less", "more"]):
            return "📄 Reading file..."
        if any(x in cmd_lower for x in ["mkdir", "touch", "cp", "mv", "rm"]):
            return "🗂️ Managing files..."
        # System info
        if any(x in cmd_lower for x in ["whoami", "pwd", "uname", "hostname", "uptime"]):
            return "🔍 Checking system info..."
        # Package management
        if any(x in cmd_lower for x in ["pip", "npm", "apt", "brew", "cargo"]):
            return "📦 Managing packages..."
        # Git
        if "git" in cmd_lower:
            return "🔀 Running git operation..."
        # Python scripts
        if "python" in cmd_lower:
            return "🐍 Running Python script..."
        # Curl/wget
        if any(x in cmd_lower for x in ["curl", "wget"]):
            return "🌐 Fetching from web..."
        # Image/video analysis
        if any(x in cmd_lower for x in ["ffmpeg", "convert", "identify", "exiftool"]):
            return "🖼️ Processing media..."
        return f"⚙️ Running command..."
    
    # File operations
    if "read" in name or "file" in name:
        return "📄 Reading file..."
    if "write" in name or "edit" in name:
        return "✏️ Editing file..."
    
    # Search
    if "search" in name or "grep" in name:
        return "🔍 Searching..."
    
    # Task management
    if "manage_tasks" in name:
        return "📋 Updating plan..."
    
    # Scheduling
    if "schedule" in name:
        return "⏰ Setting up schedule..."
    
    # Generic MCP tools
    if name.startswith("mcp_"):
        # Strip mcp_ prefix and the server name
        parts = name.split("__")
        if len(parts) > 1:
            action = parts[-1].replace("_", " ").title()
            return f"🔧 {action}..."
        return "🔧 Using tool..."
    
    return f"🔧 Working on it..."

async def _send_scheduled_message(chat_id: int, text: str, bot):
    """Callback function for the scheduler to send a message."""
    formatted = format_for_telegram(text)
    try:
        await bot.send_message(chat_id=chat_id, text=formatted, parse_mode="MarkdownV2")
        logger.info(f"Successfully sent scheduled message to {chat_id}")
    except Exception as e:
        logger.warning(f"MarkdownV2 failed for scheduled message, falling back to plain text: {e}")
        try:
            plain = strip_markdown(text)
            await bot.send_message(chat_id=chat_id, text=plain)
        except Exception as fallback_e:
            logger.error(f"Fallback send also failed: {fallback_e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I'm GOKU. I'm connected to your terminal agent.\nSend me a message to chat!")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple ping command to check connectivity."""
    logger.info(f"Ping command received from {update.effective_chat.id}")
    await update.message.reply_text("🏓 Pong! Gateway is active and listening.")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers the agent to use the voice MCP server tools."""
    logger.info(f"Voice command received from {update.effective_chat.id}")
    # Inject a system prompt that forces Goku to interact with its voice configuration.
    prompt = "[SYSTEM COMMAND]: The user just requested to manage your voice. Identify the available ElevenLabs voices using your tools, and ask the user which voice they would like to switch to. If they provided a name in their command, try to find and set it."
    # We call the main handle_message function but spoof the text.
    if update.message:
        original_text = update.message.text
        update.message.text = prompt + (f" User's exact words: {original_text}" if original_text else "")
        await handle_message(update, context)

# Make context available globally for the scheduler tool callback
# This is a bit of a hack, but necessary since the agent isn't natively bound to the telegram context
_latest_context = None
_latest_chat_id = None

async def send_telegram_notification(text: str, chat_id: int | None = None):
    """Sends a notification message to the user via Telegram."""
    global _latest_context, _latest_chat_id
    target_chat_id = chat_id or _latest_chat_id
    if _latest_context and target_chat_id:
        try:
            # Check if text needs formatting
            from server.telegram_formatter import format_for_telegram # type: ignore
            formatted_text = format_for_telegram(text)
            await _latest_context.bot.send_message(
                chat_id=target_chat_id,
                text=formatted_text,
                parse_mode="MarkdownV2"
            )
            logger.info(f"Notification sent to {target_chat_id}")
        except Exception as e:
            logger.error(f"Failed to send formatted notification: {e}")
            # Fallback to plain text if formatting fails
            try:
                await _latest_context.bot.send_message(chat_id=target_chat_id, text=text)
                logger.info(f"Fallback plain text notification sent to {target_chat_id}")
            except:
                pass
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _latest_context, _latest_chat_id, _message_dedupe_cache
    _latest_context = context
    _latest_chat_id = update.effective_chat.id
    
    # 1. Deduplication Check
    try:
        msg = update.message
        if not msg: return
        
        content_parts = []
        if msg.text: content_parts.append(msg.text)
        if msg.caption: content_parts.append(msg.caption)
        if msg.photo: content_parts.append(msg.photo[-1].file_id)
        if msg.voice: content_parts.append(msg.voice.file_id)
        if msg.document: content_parts.append(msg.document.file_id)
        if msg.video: content_parts.append(msg.video.file_id)
        
        msg_hash = hashlib.md5("".join(content_parts).encode()).hexdigest() if content_parts else None
        
        if msg_hash:
            now = datetime.now()
            _message_dedupe_cache = {h: t for h, t in _message_dedupe_cache.items() if t > now}
            if msg_hash in _message_dedupe_cache:
                logger.info(f"Ignored duplicate message from {update.effective_chat.id}")
                return
            _message_dedupe_cache[msg_hash] = now + timedelta(seconds=DEDUPE_WINDOW_SECONDS)
    except Exception as e:
        logger.error(f"Deduplication error: {e}")

    query = update.message.text or update.message.caption or ""
    is_voice = False
    attachment_path = None
    
    # 2. Handle Attachments
    try:
        if update.message.document:
            doc = update.message.document
            file = await context.bot.get_file(doc.file_id)
            attachment_path = os.path.join(UPLOAD_DIR, doc.file_name or f"doc_{doc.file_id}")
            await file.download_to_drive(attachment_path)
            
        elif update.message.photo:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            attachment_path = os.path.join(UPLOAD_DIR, f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            await file.download_to_drive(attachment_path)
            
        elif update.message.video:
            video = update.message.video
            file = await context.bot.get_file(video.file_id)
            attachment_path = os.path.join(UPLOAD_DIR, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            await file.download_to_drive(attachment_path)
            
        elif update.message.voice:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = os.path.join(UPLOAD_DIR, f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg")
            await file.download_to_drive(file_path)
            
            transcript = await transcribe_audio(file_path)
            if transcript:
                query = transcript
                is_voice = True
            else:
                await update.message.reply_text("⚠️ Could not transcribe voice note.")
                return

    except Exception as e:
        logger.error(f"Failed to download attachment: {e}")
        await update.message.reply_text(f"⚠️ Failed to download attachment: {e}")

    # 3. Define Callbacks for Broker
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    is_group = chat_type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP]
    
    sender_name = "Unknown"
    if update.effective_user:
        sender_name = update.effective_user.full_name or update.effective_user.first_name or "Unknown"
    
    if is_group:
        group_name = update.effective_chat.title or "Group"
        query = f"[GROUP: {group_name}] [{sender_name}]: {query}"

    status_msg = None

    async def status_update(text: str):
        nonlocal status_msg
        try:
            if text == "paused":
                if status_msg:
                    try:
                        await status_msg.delete()
                        status_msg = None
                    except:
                        pass
                return

            if not status_msg:
                status_msg = await update.message.reply_text(text)
            else:
                await status_msg.edit_text(text)
        except Exception:
            # Fallback for deleted status messages
            if text != "paused":
                status_msg = await update.message.reply_text(text)

    async def send_response(text: str):
        nonlocal status_msg
        try:
            # Special check for internal tool call file uploads
            # (Note: Channel Broker handles the agent execution loop)
            # The agent.run_agent stream doesn't expose tool calls directly yet in the final text
            # but we can check the history if we need to verify file delivery.
            # For now, we trust the agent's tool execution in the generator loop.

            # Formatting for Telegram
            formatted = format_for_telegram(text)
            chunks = smart_chunk(formatted)
            
            if is_voice:
                if status_msg: await status_msg.delete()
                audio_path = os.path.join(UPLOAD_DIR, f"reply_{chat_id}.mp3")
                if await generate_speech(text, audio_path):
                    with open(audio_path, 'rb') as vf:
                        await context.bot.send_voice(chat_id=chat_id, voice=vf)
                    try: os.remove(audio_path)
                    except: pass
                else:
                    await context.bot.send_message(chat_id=chat_id, text=formatted, parse_mode="MarkdownV2")
            else:
                if len(chunks) > 1:
                    if status_msg: 
                        try: await status_msg.delete()
                        except: pass
                    for c in chunks:
                        await context.bot.send_message(chat_id=chat_id, text=c, parse_mode="MarkdownV2")
                else:
                    if status_msg:
                        try:
                            await status_msg.edit_text(formatted, parse_mode="MarkdownV2")
                            # Detach status tracker so final answer isn't deleted by "paused" update
                            status_msg = None 
                        except Exception as e:
                            logger.debug(f"Edit failed (msg deleted?): {e}")
                            await update.message.reply_text(formatted, parse_mode="MarkdownV2")
                            status_msg = None
                    else:
                        await context.bot.send_message(chat_id=chat_id, text=formatted, parse_mode="MarkdownV2")
        except Exception as e:
            logger.warning(f"Response send failed: {e}")
            await context.bot.send_message(chat_id=chat_id, text=strip_markdown(text))

    # 4. Delegate to Broker
    await channel_broker.handle_incoming_message(
        session_id=str(chat_id),
        content=query,
        source="telegram",
        send_message_fn=send_response,
        status_update_fn=status_update,
        is_voice=is_voice,
        attachment_path=attachment_path,
        is_group=is_group
    )

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays current bot configuration and integration status."""
    logger.info(f"Config command received from {update.effective_chat.id}")
    
    config = config_manager.get_config()
    
    # AI Providers
    providers = []
    if config.get("OPENAI_API_KEY"): providers.append("• ✅ OpenAI")
    else: providers.append("• ❌ OpenAI")
    
    if config.get("ANTHROPIC_API_KEY"): providers.append("• ✅ Anthropic")
    else: providers.append("• ❌ Anthropic")
    
    if config.get("GOOGLE_API_KEY") or config.get("GEMINI_API_KEY"): providers.append("• ✅ Google/Gemini")
    else: providers.append("• ❌ Google/Gemini")
    
    if config.get("GITHUB_TOKEN"): providers.append("• ✅ GitHub Models")
    else: providers.append("• ❌ GitHub Models")

    # Integrations
    integrations = []
    integrations.append("• ✅ Telegram (Active)")
    
    from server.whatsapp_bot import whatsapp_bot # type: ignore
    if whatsapp_bot.is_connected:
        integrations.append("• ✅ WhatsApp (Linked)")
    else:
        integrations.append("• ❌ WhatsApp (Not Linked - run `goku config` to link)")

    # Model
    current_model = config.get("GOKU_MODEL", "default")

    report = (
        "**⚙️ Goku Configuration**\n\n"
        "**🤖 AI Providers:**\n" + "\n".join(providers) + "\n\n"
        "**🔌 Active Integrations:**\n" + "\n".join(integrations) + "\n\n"
        f"**🧠 Preferred Model:** `{current_model}`\n\n"
        "💡 _To update your configuration, use the web dashboard or edit the .env file directly._"
    )
    
    await update.message.reply_text(format_for_telegram(report), parse_mode="MarkdownV2")

async def send_telegram_message(chat_id: str, text: str):
    """Helper to send a message via the global application bot instance."""
    global _application
    if not _application or not _application.bot:
        logger.error("Cannot send Telegram message: Bot not initialized.")
        return
    try:
        from server.telegram_formatter import format_for_telegram # type: ignore
        await _application.bot.send_message(
            chat_id=chat_id,
            text=format_for_telegram(text),
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Failed to send proactive Telegram message: {e}")

async def start_telegram_bot(token: str):
    """Starts the Telegram bot application in the background."""
    global _application
    if not token: return None
    
    token = token.strip()
    
    try:
        _application = ApplicationBuilder().token(token).build()
        
        # Register interface for proactive messaging
        async def send_tg_interface(session_id: str, text: str):
            # The session_id for Telegram will be "tg_<chat_id>"
            chat_id = int(session_id.replace("tg_", ""))
            # Use the global _application.bot instance
            await _application.bot.send_message(chat_id=chat_id, text=text)

        channel_broker.register_interface("telegram", send_tg_interface)
        
        _application.add_handler(CommandHandler("start", start))
        _application.add_handler(CommandHandler("ping", ping))
        _application.add_handler(CommandHandler("voice", voice_command))
        _application.add_handler(CommandHandler("config", config_command))
        # Handle text, documents, photos, videos, and voice notes
        _application.add_handler(MessageHandler(
            (filters.TEXT | filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.VOICE) & (~filters.COMMAND), 
            handle_message
        ))
        
        await _application.initialize()
        await _application.start()
        
        # Start the background job scheduler
        scheduler.start()
        
        await _application.updater.start_polling()
        
        logger.info("Telegram Bot and Scheduler started successfully!")
        
        # Add a persistence loop so the task doesn't return (to prevent safe_startup from restarting)
        while True:
            await asyncio.sleep(3600)
            
        return _application
    except Exception as e:
        logger.error(f"Failed to start Telegram Bot: {e}")
        return None

async def schedule_telegram_message(args: dict) -> str:
    """Callback for the agent to schedule a telegram message natively."""
    global _latest_context, _latest_chat_id
    
    if not _latest_context or not hasattr(_latest_context, "bot") or not getattr(_latest_context, "bot") or not _latest_chat_id:
        return "Error: Cannot schedule message -> No active Telegram context found."
    
    delay_seconds = args.get("delay_seconds", 0)
    message_text = args.get("message_text", "")
    
    if not message_text:
        return "Error: message_text is required."
        
    try:
        run_date = datetime.now() + timedelta(seconds=float(delay_seconds))
        
        scheduler.add_job(
            _send_scheduled_message,
            'date',
            run_date=run_date,
            args=[_latest_chat_id, message_text, _latest_context.bot if _latest_context else None]
        )
        
        time_str = run_date.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Scheduled message to {_latest_chat_id} at {time_str}")
        return f"Successfully scheduled message for {time_str} (in {delay_seconds} seconds)."
    except Exception as e:
        logger.error(f"Scheduling failed: {e}")
        return f"Error scheduling task: {e}"
