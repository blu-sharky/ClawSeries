"""
Agent repository - SQLite-backed agent state and log persistence.
"""

from storage.db import get_connection


# The five canonical agent identities
AGENT_DEFINITIONS = [
    {"agent_id": "agent_director", "name": "项目总监", "default_total": 120},
    {"agent_id": "agent_chief_director", "name": "总导演", "default_total": 20},
    {"agent_id": "agent_visual", "name": "视觉总监", "default_total": 40},
    {"agent_id": "agent_prompt", "name": "提示词架构师", "default_total": 80},
    {"agent_id": "agent_editor", "name": "自动化剪辑师", "default_total": 20},
]


def init_agent_states(project_id: str):
    """Create agent state rows for a project if they don't exist."""
    conn = get_connection()
    for defn in AGENT_DEFINITIONS:
        conn.execute(
            """INSERT INTO agent_states (agent_id, project_id, name, status, total_tasks)
               VALUES (?, ?, ?, 'idle', ?)
               ON CONFLICT(agent_id, project_id) DO NOTHING""",
            (defn["agent_id"], project_id, defn["name"], defn["default_total"]),
        )
    conn.commit()


def get_agent_states(project_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM agent_states WHERE project_id = ? ORDER BY agent_id",
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_agent_state(project_id: str, agent_id: str, **kwargs):
    conn = get_connection()
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.extend([project_id, agent_id])
    conn.execute(
        f"UPDATE agent_states SET {', '.join(sets)} WHERE project_id = ? AND agent_id = ?",
        vals,
    )
    conn.commit()


def add_agent_log(project_id: str, agent_id: str, level: str, message: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO agent_logs (agent_id, project_id, level, message) VALUES (?, ?, ?, ?)",
        (agent_id, project_id, level, message),
    )
    conn.commit()


def get_agent_logs(project_id: str, agent_id: str, limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT timestamp, level, message FROM agent_logs WHERE project_id = ? AND agent_id = ? ORDER BY id DESC LIMIT ?",
        (project_id, agent_id, limit),
    ).fetchall()
    return list(reversed([dict(row) for row in rows]))
