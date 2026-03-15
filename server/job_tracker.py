import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class JobTracker:
    def __init__(self, db_path: str = "server/job_tracker.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        except Exception:
            pass # Ignore if exists or cwd is already server/

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                department TEXT NOT NULL,
                type TEXT DEFAULT 'def',
                status TEXT NOT NULL,
                payload TEXT,
                scheduled_for TEXT,
                reminder_sent INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        # Simple migration: check if 'type' column exists
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'type' not in columns:
            logger.info("Migrating job_tracker.db: Adding 'type' column")
            cursor.execute("ALTER TABLE jobs ADD COLUMN type TEXT DEFAULT 'def'")
            
        conn.commit()
        conn.close()

    def create_job(self, job_id: str, department: str, payload: Dict[str, Any], job_type: str = "def") -> bool:
        """Create a new job in the tracker."""
        now = datetime.now().isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO jobs (job_id, department, type, status, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (job_id, department, job_type, 'PENDING', json.dumps(payload), now, now)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            logger.error(f"Job {job_id} already exists.")
            return False
        except Exception as e:
            logger.error(f"Failed to create job {job_id}: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()
        return False

    def update_job_status(self, job_id: str, status: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Update the status (and optionally payload) of an existing job."""
        now = datetime.utcnow().isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if payload is not None:
                cursor.execute(
                    'UPDATE jobs SET status = ?, payload = ?, updated_at = ? WHERE job_id = ?',
                    (status, json.dumps(payload), now, job_id)
                )
            else:
                cursor.execute(
                    'UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?',
                    (status, now, job_id)
                )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update job {job_id}: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()
        return False

    def schedule_job(self, job_id: str, scheduled_time_iso: str) -> bool:
        """Set a scheduled time for a job."""
        now = datetime.utcnow().isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE jobs SET status = ?, scheduled_for = ?, reminder_sent = 0, updated_at = ? WHERE job_id = ?',
                ('SCHEDULED', scheduled_time_iso, now, job_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to schedule job {job_id}: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()
        return False

    def set_reminder_sent(self, job_id: str) -> bool:
        """Mark that the 5-minute reminder has been sent."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE jobs SET reminder_sent = 1 WHERE job_id = ?', (job_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False
        finally:
            if 'conn' in locals():
                conn.close()
        return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific job."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT department, status, payload, scheduled_for, reminder_sent, type FROM jobs WHERE job_id = ?', (job_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "job_id": job_id,
                    "department": row[0],
                    "status": row[1],
                    "payload": json.loads(row[2]) if row[2] else {},
                    "scheduled_for": row[3],
                    "reminder_sent": bool(row[4]),
                    "type": row[5]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def get_jobs_by_status(self, statuses: List[str]) -> List[Dict[str, Any]]:
        """Retrieve all jobs matching any of the provided statuses."""
        jobs = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = 'SELECT job_id, department, status, payload, scheduled_for, reminder_sent, type FROM jobs WHERE status IN ({})'.format(
                ','.join('?' * len(statuses))
            )
            cursor.execute(query, statuses)
            for row in cursor.fetchall():
                jobs.append({
                    "job_id": row[0],
                    "department": row[1],
                    "status": row[2],
                    "payload": json.loads(row[3]) if row[3] else {},
                    "scheduled_for": row[4],
                    "reminder_sent": bool(row[5]),
                    "type": row[6]
                })
            return jobs
        except Exception as e:
            logger.error(f"Failed to get jobs by status: {e}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()
        return jobs

job_tracker = JobTracker()
