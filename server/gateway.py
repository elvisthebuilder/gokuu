import asyncio
import logging
import os
import sys
import datetime

# Add project root to sys.path so we can import 'server' when running directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv # type: ignore

# Set up dedicated logging for the Gateway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s:%(levelname)s - %(message)s'
)
logger = logging.getLogger("Gateway")

# Enable debug logging for our trace modules if needed
logging.getLogger("WhatsAppBot").setLevel(logging.DEBUG)
logging.getLogger("ChannelManager").setLevel(logging.DEBUG)

load_dotenv()

async def safe_startup(coro, name: str):
    """Wrapper to catch errors during startup of background tasks."""
    try:
        logger.info(f"Starting {name}...")
        await coro
    except Exception as e:
        logger.error(f"❌ {name} failed: {e}", exc_info=True)


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
    
    # 1. Telegram Bot
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if tg_token:
        tasks.append(asyncio.create_task(safe_startup(start_telegram_bot(tg_token), "Telegram Bot")))
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not found. Telegram skipped.")

    # 2. WhatsApp Bot
    loop = asyncio.get_running_loop()
    tasks.append(asyncio.create_task(safe_startup(run_whatsapp_bot(loop), "WhatsApp Bot")))
    
    # 3. JobTracker / DEF Pipeline
    tasks.append(asyncio.create_task(safe_startup(poll_job_tracker(), "JobTracker Poller")))
    
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
