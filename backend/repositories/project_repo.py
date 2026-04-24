"""
Project repository - SQLite-backed project persistence.
"""

import json
from storage.db import get_connection


def create_project(project_id: str, title: str, conversation_id: str | None = None,
                   config: dict | None = None, status: str = "pending"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO projects (project_id, title, conversation_id, config_json, status) VALUES (?, ?, ?, ?, ?)",
        (project_id, title, conversation_id, json.dumps(config or {}, ensure_ascii=False), status),
    )
    conn.commit()
    conn.close()


def get_project(project_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    if not row:
        conn.close()
        return None
    p = dict(row)
    p["config"] = json.loads(p["config_json"]) if p["config_json"] else {}
    return p


def get_all_projects() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        p = dict(row)
        p["config"] = json.loads(p["config_json"]) if p["config_json"] else {}
        result.append(p)
    conn.close()
    return result


def update_project(project_id: str, **kwargs):
    conn = get_connection()
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k == "config" or k == "config_json":
            k = "config_json"
            v = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(project_id)
    conn.execute(
        f"UPDATE projects SET {', '.join(sets)}, updated_at = datetime('now') WHERE project_id = ?",
        vals,
    )
    conn.commit()
    conn.close()


def create_character(character_id: str, project_id: str, name: str, age: int,
                     role: str, description: str, visual_assets: dict | None = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO characters (character_id, project_id, name, age, role, description, visual_assets_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (character_id, project_id, name, age, role, description,
         json.dumps(visual_assets or {}, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_characters(project_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM characters WHERE project_id = ?", (project_id,)).fetchall()
    result = []
    for row in rows:
        c = dict(row)
        c["visual_assets"] = json.loads(c["visual_assets_json"]) if c["visual_assets_json"] else {}
        del c["visual_assets_json"]
        result.append(c)
    conn.close()
    return result


def create_episode(episode_id: str, project_id: str, episode_number: int,
                   title: str, status: str = "pending"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO episodes (episode_id, project_id, episode_number, title, status) VALUES (?, ?, ?, ?, ?)",
        (episode_id, project_id, episode_number, title, status),
    )
    conn.commit()
    conn.close()


def get_episodes(project_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM episodes WHERE project_id = ? ORDER BY episode_number",
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_episode(episode_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_episode(episode_id: str, **kwargs):
    conn = get_connection()
    sets = []
    vals = []
    json_fields = {"script", "storyboard", "assets", "script_json", "storyboard_json", "assets_json"}
    for k, v in kwargs.items():
        if k in ("script", "storyboard", "assets"):
            k = f"{k}_json"
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(episode_id)
    conn.execute(
        f"UPDATE episodes SET {', '.join(sets)}, updated_at = datetime('now') WHERE episode_id = ?",
        vals,
    )
    conn.commit()
    conn.close()


def get_completed_episode_count(project_id: str) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM episodes WHERE project_id = ? AND status = 'completed'",
        (project_id,),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0
