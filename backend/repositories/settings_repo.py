"""
Settings repository - read/write key-value settings from SQLite.
"""

from storage.db import get_connection


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value),
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def get_settings_by_prefix(prefix: str) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE ?",
        (f"{prefix}%",),
    ).fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}
