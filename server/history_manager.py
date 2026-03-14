import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class HistoryManager:
    def __init__(self, db_path: str = "goku_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for sessions and messages."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    type TEXT DEFAULT 'message',
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize history database: {e}")

    def create_session(self, session_id: str, title: str = "New Conversation"):
        """Create a new chat session."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO sessions (id, title) VALUES (?, ?)",
                (session_id, title)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error creating session: {e}")

    def add_message(self, session_id: str, role: str, content: str, msg_type: str = "message", metadata: Dict = None):
        """Add a message to a session."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Ensure session exists
            self.create_session(session_id)
            
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, type, metadata) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, msg_type, json.dumps(metadata) if metadata else None)
            )
            
            # Update session timestamp and title if it's the first user message
            if role == "user":
                cursor.execute(
                    "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (session_id,)
                )
                # Set title briefly if it's the first user message
                cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,))
                if cursor.fetchone()[0] == 1:
                    title = (content[:30] + '...') if len(content) > 30 else content
                    cursor.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding message to history: {e}")

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions sorted by last activity."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
            sessions = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return sessions
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return []

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
            messages = []
            for row in cursor.fetchall():
                msg = dict(row)
                if msg['metadata']:
                    msg['metadata'] = json.loads(msg['metadata'])
                messages.append(msg)
            conn.close()
            return messages
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []

    def delete_session(self, session_id: str):
        """Delete a session and its messages."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error deleting session: {e}")

history_manager = HistoryManager()
