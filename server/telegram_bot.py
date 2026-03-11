import logging
import asyncio
import os
from typing import cast
from datetime import datetime, timedelta
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from server.agent import agent
from server.telegram_formatter import format_for_telegram, smart_chunk, strip_markdown

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

# Make context available globally for the scheduler tool callback
# This is a bit of a hack, but necessary since the agent isn't natively bound to the telegram context
_latest_context = None
_latest_chat_id = None

async def send_telegram_notification(text: str, chat_id: int = None):
    """Sends a notification message to the user via Telegram."""
    global _latest_context, _latest_chat_id
    target_chat_id = chat_id or _latest_chat_id
    if _latest_context and target_chat_id:
        try:
            # Check if text needs formatting
            from server.telegram_formatter import format_markdown_v2
            formatted_text = format_markdown_v2(text)
            await _latest_context.bot.send_message(
                chat_id=target_chat_id,
                text=formatted_text,
                parse_mode="MarkdownV2"
            )
            logger.info(f"Notification sent to {target_chat_id}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            # Fallback to plain text if formatting fails
            try:
                await _latest_context.bot.send_message(chat_id=target_chat_id, text=text)
            except:
                pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _latest_context, _latest_chat_id
    _latest_context = context
    _latest_chat_id = update.effective_chat.id
    
    query = update.message.text or update.message.caption or ""
    
    # Check for @mention summoning
    is_summon = False
    if query.strip().startswith("@"):
        import re
        match = re.match(r"@(\w+)\s+(.*)", query.strip())
        if match:
            skill_name = match.group(1).lower()
            intent = match.group(2)
            # Route to skill via a system instruction that forces the tool call
            # We wrap it in a special instruction that the agent will see first
            query = f"[USER SUMMONED @{skill_name}]: {intent}"
            is_summon = True
            logger.info(f"User summoned @{skill_name} with intent: {intent}")
    
    # Handle Attachments
    attachment_info = ""
    file_type_str = "file"
    try:
        if update.message.document:
            doc = update.message.document
            file = await context.bot.get_file(doc.file_id)
            file_path = os.path.join(UPLOAD_DIR, doc.file_name)
            
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                file_type_str = "video"
            elif ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.md']:
                file_type_str = "document"
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                file_type_str = "image"
            elif ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json', '.sh', '.cpp', '.c']:
                file_type_str = "code file"
                
            await file.download_to_drive(file_path)
            attachment_info = f"[File Received: {file_path}]"
            logger.info(f"Downloaded document to {file_path}")
            
        elif update.message.photo:
            # Take the largest photo size
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            # Use timestamp for photo names
            ext = ".jpg" # Default for telegram photos
            file_type_str = "image"
            filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            await file.download_to_drive(file_path)
            attachment_info = f"[Photo Received: {file_path}]"
            logger.info(f"Downloaded photo to {file_path}")
            
        elif update.message.video:
            video = update.message.video
            file = await context.bot.get_file(video.file_id)
            ext = os.path.splitext(video.file_name or ".mp4")[1].lower()
            file_type_str = "video"
            filename = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            await file.download_to_drive(file_path)
            attachment_info = f"[File Received: {file_path}]"
            logger.info(f"Downloaded video to {file_path}")
            
    except Exception as e:
        logger.error(f"Failed to download attachment: {e}")
        await update.message.reply_text(f"⚠️ Failed to download attachment: {e}")

    if attachment_info and not query:
        # User uploaded a file with no message — add an implicit prompt to force conversational analysis
        implicit_prompt = f"(System Action: The user just uploaded this {file_type_str} without any instructions. Please analyze its contents in detail and respond conversationally. Do not just say 'Done' or 'Waiting for instructions'. Instead, describe what you see and ask the user what they would like to do with it.)"
        full_query = f"{attachment_info} {implicit_prompt}"
    elif is_summon:
        # For summons, we want the agent to call the specific tool immediately
        import re
        mention_match = re.search(r"@(\w+)", (update.message.text or update.message.caption or "").strip())
        skill_name = mention_match.group(1).lower() if mention_match else "unknown"
        # The agent will look for openclaw_agent_<skill_name> or openclaw_skill_<skill_name>
        full_query = f"{attachment_info} [SYSTEM: The user explicitly mentioned @{skill_name}. Find the most appropriate 'openclaw_' tool (agent or skill) and CALL it IMMEDIATELY with this intent: {query.replace(f'[USER SUMMONED @{skill_name}]: ', '')}]"
    else:
        full_query = f"{attachment_info} {query}".strip()
        
    if not full_query: return
    
    # Send initial status
    if attachment_info:
        status_msg = await update.message.reply_text(f"⏳ {file_type_str.capitalize()} received. Analyzing your {file_type_str}, this may take a moment...")
    else:
        status_msg = await update.message.reply_text("🤔 Thinking...")
    
    response_text = ""
    try:
        # Use the global agent instance
        gen = agent.run_agent(full_query, source="telegram")
        try:
            while True:
                event = await anext(gen)
                if event["type"] == "tool_call":
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
                    try:
                        status = _describe_tool_action(event.get('name', ''), event.get('args', {}))
                        await status_msg.edit_text(status)
                    except Exception:
                        pass 
                elif event["type"] == "message":
                    # Accumulate multi-step responses
                    chunk = event["content"]
                    if chunk:
                        if response_text:
                            response_text += "\n\n"
                        response_text += chunk
        except StopAsyncIteration:
            pass
            
        # After the loop finishes (either naturally or via StopAsyncIteration), check if the agent triggered the send_file tool
        for msg in agent.history[-1:]: # Only check the most recent turn
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if tc.get("function", {}).get("name") == "send_telegram_file":
                        try:
                            import json
                            args_str = tc["function"].get("arguments", "{}")
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            if isinstance(args, str): args = json.loads(args)
                            file_path = args.get("file_path")
                            caption = args.get("caption", "")
                            
                            if file_path and os.path.exists(file_path):
                                await status_msg.edit_text(f"📤 Uploading file: {os.path.basename(file_path)}...")
                                # Use send_document for general files
                                await context.bot.send_document(
                                    chat_id=update.effective_chat.id,
                                    document=open(file_path, 'rb'),
                                    caption=caption
                                )
                                # Clear status message if successful
                                response_text = "✅ File sent successfully."
                            else:
                                response_text += f"\n\n❌ Error: Could not find file at '{file_path}'"
                        except Exception as e:
                            logger.error(f"Failed to send file: {e}")
                            response_text += f"\n\n❌ Failed to upload file: {e}"
            raw_text = str(response_text)
            formatted_text = format_for_telegram(raw_text)
            chunks = smart_chunk(formatted_text)
            
            if len(chunks) > 1:
                # Multiple chunks — send as separate messages
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                for chunk in chunks:
                    try:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=chunk,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        logger.warning(f"MarkdownV2 chunk failed, sending plain: {e}")
                        plain_chunk = strip_markdown(chunk)
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=plain_chunk
                        )
            else:
                # Single message — edit the status message
                try:
                    await status_msg.edit_text(formatted_text, parse_mode="MarkdownV2")
                except Exception as e:
                    logger.warning(f"MarkdownV2 edit failed, falling back to plain text: {e}")
                    try:
                        plain = strip_markdown(raw_text)
                        await status_msg.edit_text(plain)
                    except Exception:
                        await status_msg.edit_text(raw_text[:4096])
        else:
            await status_msg.edit_text("✅ Done")
            
    except Exception as e:
        logger.error(f"Error processing telegram message: {e}")
        err_msg = str(e).lower()
        
        # Classify the error for a user-friendly message
        if "not reachable" in err_msg or "connect" in err_msg or "offline" in err_msg:
            user_error = "⚠️ The AI service is currently offline. Please try again in a moment."
        elif "timeout" in err_msg or "timed out" in err_msg:
            user_error = "⏳ The AI took too long to respond (it may be loading). Please try again."
        elif "not found" in err_msg and ("model" in err_msg or "ollama" in err_msg):
            user_error = "⚠️ The AI model isn't available right now. Please check the server configuration."
        elif "500" in err_msg or "server error" in err_msg or "service error" in err_msg:
            user_error = "⚠️ The AI service encountered an internal error. It may recover on its own — try again in a moment."
        elif "auth" in err_msg or "api key" in err_msg:
            user_error = "🔑 Authentication error with the AI provider. Please check your API keys."
        else:
            user_error = f"❌ Something went wrong: {str(e)[:200]}"
        
        try:
            await status_msg.edit_text(user_error)
        except Exception:
            pass

async def start_telegram_bot(token: str):
    """Starts the Telegram bot application in the background."""
    global _application
    if not token: return None
    
    token = token.strip()
    
    try:
        _application = ApplicationBuilder().token(token).build()
        
        _application.add_handler(CommandHandler("start", start))
        _application.add_handler(CommandHandler("ping", ping))
        # Handle text, documents, and photos
        _application.add_handler(MessageHandler(
            (filters.TEXT | filters.Document.ALL | filters.PHOTO) & (~filters.COMMAND), 
            handle_message
        ))
        
        await _application.initialize()
        await _application.start()
        
        # Start the background job scheduler
        scheduler.start()
        
        await _application.updater.start_polling()
        
        logger.info("Telegram Bot and Scheduler started successfully!")
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
