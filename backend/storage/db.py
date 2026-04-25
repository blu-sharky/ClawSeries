"""
SQLite database connection and schema initialization.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled.
    
    Uses WAL mode for better concurrent read/write performance
    and busy_timeout to wait for locks instead of failing immediately.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections that ensures cleanup."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize all database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            conversation_id TEXT,
            config_json TEXT,
            status TEXT DEFAULT 'draft',
            progress INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Characters table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            character_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            age TEXT,
            role TEXT,
            description TEXT,
            visual_assets_json TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Episodes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            episode_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            episode_number INTEGER NOT NULL,
            title TEXT,
            status TEXT DEFAULT 'draft',
            script_json TEXT,
            storyboard_json TEXT,
            assets_json TEXT,
            progress INTEGER DEFAULT 0,
            duration INTEGER,
            video_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            initial_idea TEXT,
            state TEXT DEFAULT 'collecting_requirements',
            current_phase INTEGER DEFAULT 1,
            project_id TEXT,
            collected_info TEXT,
            script_outline_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            questions_json TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
        )
    """)

    # Tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            episode_id TEXT,
            shot_id TEXT,
            task_type TEXT NOT NULL,
            agent_id TEXT,
            input_json TEXT,
            output_json TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Shots table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shots (
            shot_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            shot_number INTEGER NOT NULL,
            description TEXT,
            camera_movement TEXT,
            duration INTEGER,
            status TEXT DEFAULT 'pending',
            video_url TEXT,
            first_frame_path TEXT,
            image_prompt TEXT,
            video_prompt TEXT,
            FOREIGN KEY (episode_id) REFERENCES episodes(episode_id),
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Shot traces table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shot_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shot_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            agent_id TEXT,
            stage TEXT,
            chroma_hits_json TEXT,
            assets_referenced_json TEXT,
            prompt_summary TEXT,
            prompt_hash TEXT,
            provider_name TEXT,
            model_name TEXT,
            output_path TEXT,
            cache_hit INTEGER DEFAULT 0,
            error_reason TEXT,
            duration_ms INTEGER,
            retry_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (shot_id) REFERENCES shots(shot_id),
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Agent states table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_states (
            agent_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            name TEXT,
            status TEXT DEFAULT 'idle',
            total_tasks INTEGER DEFAULT 0,
            current_task TEXT,
            completed_tasks INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0,
            PRIMARY KEY (agent_id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Agent logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            message TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Production events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            episode_id TEXT,
            shot_id TEXT,
            agent_id TEXT,
            stage TEXT,
            event_type TEXT,
            title TEXT,
            message TEXT,
            payload_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Project stages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_stages (
            project_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            PRIMARY KEY (project_id, stage),
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Assets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            episode_id TEXT,
            type TEXT NOT NULL,
            name TEXT,
            description TEXT,
            prompt TEXT,
            image_path TEXT,
            anchor_prompt TEXT,
            reference_image_path TEXT,
            embedding_ref TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)

    # Dubbing tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dubbing_tasks (
            task_id TEXT PRIMARY KEY,
            source_video_path TEXT NOT NULL,
            target_language TEXT NOT NULL,
            source_language TEXT,
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            current_step TEXT,
            output_video_path TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
    """)

    # Migrations: add columns that may not exist in older databases
    migrations = [
        ("ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0", "retry_count"),
        ("ALTER TABLE shots ADD COLUMN image_prompt TEXT", "image_prompt"),
        ("ALTER TABLE shots ADD COLUMN video_prompt TEXT", "video_prompt"),
    ]
    for sql, col in migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()
