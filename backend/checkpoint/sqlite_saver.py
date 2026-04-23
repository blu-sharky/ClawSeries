"""LangGraph SQLite checkpointer configuration.

Uses a separate database file to avoid lock contention with the
main application database.
"""

import aiosqlite

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import DATA_DIR

# Separate DB for LangGraph checkpoints to avoid locking the main DB
CHECKPOINT_DB_PATH = DATA_DIR / "langgraph_checkpoints.db"

# Module-level persistent connection for the checkpointer
_conn: aiosqlite.Connection | None = None
_saver: AsyncSqliteSaver | None = None


async def get_checkpointer() -> AsyncSqliteSaver:
    """Create or return the LangGraph async SQLite checkpointer.

    Uses a separate database file from the main app to avoid
    SQLite lock contention between the sync app connection and
    the async checkpoint connection.

    LangGraph will create its own tables (checkpoints, checkpoint_blobs,
    checkpoint_writes) inside this database.
    """
    global _conn, _saver
    if _saver is not None:
        return _saver

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(str(CHECKPOINT_DB_PATH))
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA busy_timeout=5000")
    _saver = AsyncSqliteSaver(_conn)
    return _saver
