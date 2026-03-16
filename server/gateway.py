import asyncio
import logging
import os
import sys
import datetime

# Add project root to sys.path so we can import 'server' when running directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv # type: ignore

# Set up dedicated logging for the Gateway
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "goku.log")

# Setup root-level logging to file
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

# Also log to stdout for systemd capture
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(console_handler)

logger = logging.getLogger("Gateway")

# Enable debug logging for our trace modules if needed
logging.getLogger("WhatsAppBot").setLevel(logging.DEBUG)
logging.getLogger("ChannelManager").setLevel(logging.DEBUG)

load_dotenv()

async def safe_startup(coro_fn, name: str):
    """Wrapper to catch errors and restart failed background tasks."""
    while True:
        try:
            logger.info(f"Starting {name}...")
            # We pass a function that returns a coroutine to allow restarting
            await coro_fn()
            logger.warning(f"⚠️ {name} service returned early. Restarting in 10s...")
        except Exception as e:
            logger.error(f"❌ {name} failed: {e}", exc_info=True)
            logger.info(f"Retrying {name} in 10s...")
        await asyncio.sleep(10)


async def poll_job_tracker():
    """Background loop to check for pending approvals and scheduled jobs."""
    from server.job_tracker import job_tracker  # type: ignore
    from server.agent import agent  # type: ignore
    
    logger.info("DEF JobTracker poller initiated.")
    while True:
        try:
            now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) # Keep it naive for SQLite but accurate
            
            # 1. Check for Pending Approvals
            approvals = job_tracker.get_jobs_by_status(["AWAITING_APPROVAL"])
            for job in approvals:
                # We use reminder_sent as a dirty flag to avoid spamming the user
                if not job.get("reminder_sent"):
                    msg = f"🔔 **Audit Department Proposal**\n\n{job.get('payload', {}).get('plan', 'No plan provided.')}\n\nDo you want to implement this now, or schedule it for later?"
                    # For simplicity, log it. In a full system, you'd route this to the specific user chat.
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


async def main():
    """Main entry point for the all-in-one background server."""
    logger.info("🐉 Goku Background Gateway Starting...")
    
    # Must import these inside the async loop to avoid event loop issues with some libraries
    from server.telegram_bot import start_telegram_bot  # type: ignore
    from server.whatsapp_bot import run_whatsapp_bot  # type: ignore
    from server.config_manager import config_manager # type: ignore
    
    tasks = []
    
    # 1. Telegram Bot (Long-polling)
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        tasks.append(safe_startup(lambda: start_telegram_bot(telegram_token), "Telegram Bot"))
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not found. Telegram skipped.")

    # 2. WhatsApp Bot (LID-aware Hyper-Resilience)
    loop = asyncio.get_running_loop()
    wa_linked = config_manager.get_key("WHATSAPP_LINKED") == "true"
    if wa_linked:
        # Note: WhatsApp bot blocking thread-safe call
        tasks.append(safe_startup(lambda: run_whatsapp_bot(loop), "WhatsApp Bot"))
    else:
        logger.warning("WHATSAPP_LINKED not true. WhatsApp Bot skipped.")
    
    # 3. Scheduler Manager (Autonomous Tasks)
    from server.scheduler_manager import scheduler_manager # type: ignore
    async def run_scheduler():
        scheduler_manager.start()
        while True: await asyncio.sleep(3600)
    tasks.append(safe_startup(run_scheduler, "Scheduler Manager"))
    
    # 4. Job Tracker Poller
    tasks.append(safe_startup(poll_job_tracker, "Job Tracker Poller"))
    
    # Run them all concurrently forever
    logger.info("All services dispatched. Gateway is now running.")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Gateway crashed: {e}", exc_info=True)
