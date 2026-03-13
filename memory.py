"""
Memory Module for ABC AI
SQLite-based persistent memory
"""

import json
import sqlite3
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentMemory:
    """Manages persistent memory for ABC AI Agent"""
    
    def __init__(self, db_path: str = "agent_memory.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Context/knowledge table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                category TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Agent actions history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                action_data TEXT NOT NULL,
                result TEXT,
                success BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Agent memory database initialized")
    
    def store_message(self, session_id: str, role: str, content: str, metadata: Dict = None):
        """Store a conversation message"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations (session_id, role, content, metadata)
            VALUES (?, ?, ?, ?)
        ''', (session_id, role, content, json.dumps(metadata) if metadata else None))
        
        conn.commit()
        conn.close()
        
        # Optional: Auto-trim only if session gets extremely large (10000+ messages)
        # This prevents database corruption from runaway sessions
        # Most conversations won't hit this limit
        self._trim_session_if_excessive(session_id, max_messages=10000)
    
    def get_conversation_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get conversation history for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT role, content, metadata, timestamp
            FROM conversations
            WHERE session_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        ''', (session_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'role': row[0],
                'content': row[1],
                'metadata': json.loads(row[2]) if row[2] else None,
                'timestamp': row[3]
            }
            for row in rows
        ]
    
    def store_context(self, key: str, value: Any, category: str = None):
        """Store context/knowledge"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO context (key, value, category, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (key, json.dumps(value), category, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_context(self, key: str) -> Optional[Any]:
        """Get context value"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT value FROM context WHERE key = ?
        ''', (key,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
    
    def get_context_by_category(self, category: str) -> Dict[str, Any]:
        """Get all context in a category"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT key, value FROM context WHERE category = ?
        ''', (category,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return {row[0]: json.loads(row[1]) for row in rows}
    
    def log_action(self, action_type: str, action_data: Dict, result: str = None, success: bool = True):
        """Log an agent action"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO actions (action_type, action_data, result, success)
            VALUES (?, ?, ?, ?)
        ''', (action_type, json.dumps(action_data), result, success))
        
        conn.commit()
        conn.close()
    
    def get_recent_actions(self, action_type: str = None, limit: int = 20) -> List[Dict]:
        """Get recent actions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if action_type:
            cursor.execute('''
                SELECT action_type, action_data, result, success, timestamp
                FROM actions
                WHERE action_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (action_type, limit))
        else:
            cursor.execute('''
                SELECT action_type, action_data, result, success, timestamp
                FROM actions
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'action_type': row[0],
                'action_data': json.loads(row[1]),
                'result': row[2],
                'success': row[3],
                'timestamp': row[4]
            }
            for row in rows
        ]
    
    def clear_session(self, session_id: str):
        """Clear conversation history for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM conversations WHERE session_id = ?
        ''', (session_id,))
        
        conn.commit()
        conn.close()
    
    def _trim_session_if_excessive(self, session_id: str, max_messages: int = 10000):
        """Only trim if session has excessive messages (safety measure)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check current count
        cursor.execute('''
            SELECT COUNT(*) FROM conversations WHERE session_id = ?
        ''', (session_id,))
        count = cursor.fetchone()[0]
        
        # Only trim if extremely excessive (prevents runaway DB growth)
        if count > max_messages:
            # Keep last 90% to preserve most context
            keep_count = int(max_messages * 0.9)
            
            cursor.execute('''
                DELETE FROM conversations
                WHERE session_id = ?
                AND id NOT IN (
                    SELECT id FROM conversations
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
            ''', (session_id, session_id, keep_count))
            
            deleted = cursor.rowcount
            conn.commit()
            logging.getLogger(__name__).warning(
                f"Session {session_id} had {count} messages, trimmed {deleted} old ones"
            )
        
        conn.close()
    
    def cleanup_old_sessions(self, days: int = 30):
        """Remove sessions older than N days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM conversations
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        ''', (days,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logging.getLogger(__name__).info(f"Cleaned up {deleted} messages older than {days} days")