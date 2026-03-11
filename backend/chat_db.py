"""
Chat history persistence using SQLite.
Zero extra dependencies — uses Python's built-in sqlite3.
DB lives at data/chat.db alongside the existing jobs store.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional

def _get_db_path() -> Path:
    """Resolve DB path from settings so it works regardless of cwd."""
    try:
        from backend.core.settings import settings
        return Path(settings.data_dir) / "chat.db"
    except Exception:
        return Path("data/chat.db")


def _get_conn() -> sqlite3.Connection:
    """Open (or create) the SQLite DB and return a connection."""
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the chat_messages table if it doesn't exist yet."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id      TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                sources     TEXT,
                wants_clip  INTEGER DEFAULT 0,
                followups   TEXT,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_job_id ON chat_messages(job_id)")
        conn.commit()


class ChatDB:
    """Simple CRUD helper for chat history."""

    @staticmethod
    def save_message(
        job_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict]] = None,
        wants_clip: bool = False,
        followups: Optional[List[str]] = None,
    ) -> int:
        """Persist a single chat message. Returns the new row id."""
        with _get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO chat_messages
                    (job_id, role, content, sources, wants_clip, followups)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    role,
                    content,
                    json.dumps(sources) if sources else None,
                    1 if wants_clip else 0,
                    json.dumps(followups) if followups else None,
                ),
            )
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def get_history(job_id: str) -> List[Dict]:
        """
        Return all messages for a job ordered oldest-first.
        Each dict is shaped the same way the frontend ChatTab renders them.
        """
        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, sources, wants_clip, followups, created_at
                FROM   chat_messages
                WHERE  job_id = ?
                ORDER  BY id ASC
                """,
                (job_id,),
            ).fetchall()

        messages = []
        for r in rows:
            msg: Dict = {
                "id":         f"db-{r['id']}",
                "role":       r["role"],
                "content":    r["content"],
                "created_at": r["created_at"],
                "streaming":  False,
            }
            if r["sources"]:
                try:
                    msg["sources"] = json.loads(r["sources"])
                except Exception:
                    msg["sources"] = []
            if r["wants_clip"]:
                msg["wants_clip"] = True
            if r["followups"]:
                try:
                    msg["followups"] = json.loads(r["followups"])
                except Exception:
                    pass
            messages.append(msg)
        return messages

    @staticmethod
    def delete_history(job_id: str) -> int:
        """Delete all messages for a job. Returns number of rows deleted."""
        with _get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM chat_messages WHERE job_id = ?", (job_id,)
            )
            conn.commit()
            return cur.rowcount

    @staticmethod
    def get_llm_history(job_id: str, last_n: int = 12) -> List[Dict]:
        """
        Return the last N messages in LLM-ready format:
          [{"role": "user"|"assistant", "content": "..."}]
        Used to pass conversation context on each new message so we
        don't need the frontend to send the full history anymore.
        """
        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM   chat_messages
                WHERE  job_id = ?
                ORDER  BY id DESC
                LIMIT  ?
                """,
                (job_id, last_n),
            ).fetchall()

        # Reverse so oldest-first for the LLM
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# Initialise DB when module is first imported
init_db()
print(f"✅ Chat DB ready at: {_get_db_path().resolve()}")
