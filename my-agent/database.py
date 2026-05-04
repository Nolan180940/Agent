"""
SQLite database operations for task logging, configuration, and scheduled rules.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


class Database:
    """SQLite database manager for agent data persistence."""
    
    def __init__(self, db_path: str = "agent.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tasks table - stores workflow definitions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    workflow_json TEXT NOT NULL,
                    cron_expression TEXT,
                    is_trusted BOOLEAN DEFAULT FALSE,
                    is_enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Logs table - stores execution logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            
            # Tool executions table - stores tool call history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    tool_name TEXT NOT NULL,
                    parameters TEXT,
                    result TEXT,
                    status TEXT NOT NULL,
                    confirmed_by_user BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            
            # Settings table - stores user preferences
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    # Task operations
    def create_task(self, name: str, workflow: List[Dict], 
                    description: str = "", cron: str = None, 
                    is_trusted: bool = False) -> int:
        """Create a new task/workflow."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (name, description, workflow_json, cron_expression, is_trusted)
                VALUES (?, ?, ?, ?, ?)
            """, (name, description, json.dumps(workflow), cron, is_trusted))
            conn.commit()
            return cursor.lastrowid
    
    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get a task by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_tasks(self) -> List[Dict]:
        """Get all tasks."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def update_task(self, task_id: int, **kwargs) -> bool:
        """Update a task."""
        if not kwargs:
            return False
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [task_id]
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, values)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # Log operations
    def add_log(self, level: str, message: str, task_id: int = None, 
                details: str = None) -> int:
        """Add a log entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO logs (task_id, level, message, details)
                VALUES (?, ?, ?, ?)
            """, (task_id, level, message, details))
            conn.commit()
            return cursor.lastrowid
    
    def get_logs(self, limit: int = 100, task_id: int = None) -> List[Dict]:
        """Get recent logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if task_id:
                cursor.execute(
                    "SELECT * FROM logs WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
                    (task_id, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            return [dict(row) for row in cursor.fetchall()]
    
    def clear_logs(self, older_than_days: int = 7) -> int:
        """Clear old logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM logs 
                WHERE created_at < datetime('now', ?)
            """, (f'-{older_than_days} days',))
            conn.commit()
            return cursor.rowcount
    
    # Tool execution operations
    def record_tool_execution(self, tool_name: str, parameters: Dict, 
                              result: str, status: str, 
                              task_id: int = None, 
                              confirmed_by_user: bool = True) -> int:
        """Record a tool execution."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_executions 
                (task_id, tool_name, parameters, result, status, confirmed_by_user)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, tool_name, json.dumps(parameters), 
                  result, status, confirmed_by_user))
            conn.commit()
            return cursor.lastrowid
    
    def get_tool_executions(self, limit: int = 50) -> List[Dict]:
        """Get recent tool executions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tool_executions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # Settings operations
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except json.JSONDecodeError:
                    return row['value']
            return default
    
    def set_setting(self, key: str, value: Any) -> bool:
        """Set a setting value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, json.dumps(value) if not isinstance(value, str) else value))
            conn.commit()
            return True
