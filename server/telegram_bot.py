import logging
import asyncio
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from server.agent import agent

# Configure logging for bot
logger = logging.getLogger("TelegramBot")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I'm GOKU. I'm connected to your terminal agent.\nSend me a message to chat!")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple ping command to check connectivity."""
    await update.message.reply_text("🏓 Pong! Gateway is active and listening.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    if not query: return
    
    # Send initial status
    status_msg = await update.message.reply_text("🤔 Thinking...")
    
    response_text = ""
    try:
        # Use the global agent instance
        async for event in agent.run_agent(query):
            if event["type"] == "tool_call":
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
                try:
                    await status_msg.edit_text(f"🛠️ Executing: {event['name']}...")
                except Exception:
                    pass 
            elif event["type"] == "message":
                # Accumulate multi-step responses
                chunk = event["content"]
                if chunk:
                    if response_text:
                        response_text += "\n\n"
                    response_text += chunk
        
        if response_text:
            if len(response_text) > 4000:
                for x in range(0, len(response_text), 4000):
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text[x:x+4000], parse_mode="Markdown")
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            else:
                try:
                    await status_msg.edit_text(response_text, parse_mode="Markdown")
                except Exception:
                    # Fallback if markdown fails
                    await status_msg.edit_text(response_text)
        else:
            await status_msg.edit_text("✅ Done (No textual output)")
            
    except Exception as e:
        logger.error(f"Error processing telegram message: {e}")
        try:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
        except Exception:
            pass

async def start_telegram_bot(token: str):
    """Starts the Telegram bot application in the background."""
    if not token: return None
    
    try:
        application = ApplicationBuilder().token(token).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("ping", ping))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("Telegram Bot started successfully!")
        return application
    except Exception as e:
        logger.error(f"Failed to start Telegram Bot: {e}")
        return None
