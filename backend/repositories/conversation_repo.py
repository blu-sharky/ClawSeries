"""
Conversation repository - SQLite-backed conversation persistence.
"""

import json
from storage.db import get_connection


def create_conversation(conv_id: str, initial_idea: str, state: str = "collecting_requirements"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (conversation_id, initial_idea, state) VALUES (?, ?, ?)",
        (conv_id, initial_idea, state),
    )
    conn.commit()
    conn.close()


def get_conversation(conv_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM conversations WHERE conversation_id = ?", (conv_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    return dict(row)


def update_conversation(conv_id: str, **kwargs):
    conn = get_connection()
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k == "collected_info" or k == "script_outline_json":
            v = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(conv_id)
    conn.execute(
        f"UPDATE conversations SET {', '.join(sets)}, updated_at = datetime('now') WHERE conversation_id = ?",
        vals,
    )
    conn.commit()
    conn.close()


def add_message(conv_id: str, role: str, content: str, questions_json: str | list | None = None):
    conn = get_connection()
    if questions_json is not None and not isinstance(questions_json, str):
        questions_json = json.dumps(questions_json, ensure_ascii=False)
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, questions_json) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, questions_json),
    )
    conn.commit()
    conn.close()


def get_messages(conv_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content, questions_json, timestamp FROM messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall()
    result = []
    for row in rows:
        msg = {"role": row["role"], "content": row["content"], "timestamp": row["timestamp"]}
        if row["questions_json"]:
            msg["questions"] = json.loads(row["questions_json"])
        result.append(msg)
    conn.close()
    return result
