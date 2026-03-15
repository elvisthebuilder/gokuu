import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore
from apscheduler.triggers.cron import CronTrigger # type: ignore
from .job_tracker import job_tracker
from .channel_manager import channel_broker

logger = logging.getLogger("SchedulerManager")

class SchedulerManager:
    """Centralized manager for all time-based tasks in Goku."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def start(self):
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("SchedulerManager started.")
            # Load existing recurring jobs from DB
            self.sync_from_db()

    def stop(self):
        if self._is_running:
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("SchedulerManager stopped.")

    def sync_from_db(self):
        """Load all 'autonomous' jobs from the tracker and schedule them."""
        # Note: In this version, we focus on recurring autonomous tasks
        # For simple one-off 'SCHEDULED' jobs, gateway.py's poller handles them.
        try:
            # We'll use a specific status Like 'ACTIVE' for recurring jobs
            jobs = job_tracker.get_jobs_by_status(["ACTIVE", "SCHEDULED"])
            for job in jobs:
                if job.get("type") == "autonomous":
                    self.add_job_from_record(job)
        except Exception as e:
            logger.error(f"Failed to sync scheduler from DB: {e}")

    def add_job_from_record(self, job: Dict[str, Any]):
        """Translates a DB record into an active APScheduler job."""
        job_id = job["job_id"]
        payload = job.get("payload", {})
        cron = payload.get("cron")
        prompt = payload.get("prompt")
        channel = payload.get("channel")
        session_id = payload.get("session_id")
        group_name = payload.get("group_name")

        if not cron or not prompt or not channel or not session_id:
            logger.warning(f"Skipping job {job_id}: Missing required payload data.")
            return

        try:
            # Remove if already exists to prevent duplicates on resync
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            self.scheduler.add_job(
                self._execute_autonomous_task,
                CronTrigger.from_crontab(cron),
                id=job_id,
                args=[channel, session_id, prompt, job_id, group_name],
                replace_existing=True
            )
            logger.info(f"Scheduled recurring job {job_id} ('{cron}') for {channel}:{session_id} (Group: {group_name})")
        except Exception as e:
            logger.error(f"Failed to add job {job_id} to scheduler: {e}")

    async def _execute_autonomous_task(self, channel: str, session_id: str, prompt: str, job_id: str, group_name: Optional[str] = None):
        """Trigger the agent proactively."""
        logger.info(f"⏰ Triggering autonomous job {job_id} for {channel}:{session_id}")
        try:
            await channel_broker.trigger_autonomous_agent(
                source=channel,
                session_id=session_id,
                prompt=prompt,
                group_name=group_name
            )
        except Exception as e:
            logger.error(f"Execution of job {job_id} failed: {e}")

    def add_autonomous_job(self, name: str, cron: str, prompt: str, channel: str, session_id: str, group_name: Optional[str] = None) -> bool:
        """Create a new autonomous job, save to DB, and schedule it."""
        job_id = f"auto_{name}_{session_id}".replace(":", "_")
        payload = {
            "cron": cron,
            "prompt": prompt,
            "channel": channel,
            "session_id": session_id,
            "group_name": group_name
        }
        
        # Save to DB
        success = job_tracker.create_job(
            job_id=job_id,
            department="autonomous",
            payload=payload,
            job_type="autonomous"
        )
        if success:
            job_tracker.update_job_status(job_id, "ACTIVE")
            job = job_tracker.get_job(job_id)
            if job:
                self.add_job_from_record(job)
                return True
        return False

    def remove_job(self, job_id: str) -> bool:
        """Remove a job from both scheduler and DB."""
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            job_tracker.update_job_status(job_id, "DELETED") # Or just delete record
            logger.info(f"Removed job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Error removing job {job_id}: {e}")
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all active recurring jobs."""
        jobs = []
        for j in self.scheduler.get_jobs():
            jobs.append({
                "id": j.id,
                "next_run": j.next_run_time.isoformat() if j.next_run_time else None
            })
        return jobs

scheduler_manager = SchedulerManager()
