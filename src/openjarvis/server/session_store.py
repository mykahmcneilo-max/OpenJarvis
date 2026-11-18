"""SQLite-backed session store for channel conversations."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)

_MAX_HISTORY_TURNS = 20


def _db_locked(func):
    """Serialize access to a session-store connection shared by worker threads."""

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        with self._db_lock:
            return func(self, *args, **kwargs)

    return wrapped


class SessionStore:
    """Manages per-sender, per-channel conversation sessions.

    Each session tracks conversation history, notification preferences,
    and pending long responses for the ``/more`` command.
    """

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            db_path = str(get_config_dir() / "sessions.db")
        # Ensure the parent directory exists (skip for :memory:)
        if db_path != ":memory:":
            from openjarvis.security.file_utils import secure_create

            secure_create(Path(db_path))
        self._db_lock = threading.RLock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @_db_locked
    def _create_tables(self) -> None:
        self._db.executescript(
            """\
            CREATE TABLE IF NOT EXISTS channel_sessions (
                sender_id                    TEXT    NOT NULL,
                channel_type                 TEXT    NOT NULL,
                conversation_history         TEXT    NOT NULL DEFAULT '[]',
                preferred_notification_channel TEXT,
                pending_response             TEXT,
                created_at                   TIMESTAMP DEFAULT (datetime('now')),
                updated_at                   TIMESTAMP DEFAULT (datetime('now')),
                PRIMARY KEY (sender_id, channel_type)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON channel_sessions (updated_at);
            -- Durable, display-oriented log of channel messages (the rolling
            -- history above is only the model's short-term context).
            CREATE TABLE IF NOT EXISTS channel_messages (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id  TEXT    NOT NULL,
                channel_type     TEXT    NOT NULL,
                role             TEXT    NOT NULL,
                content          TEXT    NOT NULL DEFAULT '',
                attachments      TEXT    NOT NULL DEFAULT '[]',
                agent            TEXT    NOT NULL DEFAULT '',
                model            TEXT    NOT NULL DEFAULT '',
                delivery_status  TEXT    NOT NULL DEFAULT '',
                delivery_error   TEXT    NOT NULL DEFAULT '',
                message_handle   TEXT    NOT NULL DEFAULT '',
                created_at       TIMESTAMP
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_channel_messages_conv
                ON channel_messages (conversation_id, id);
            """
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Durable message log (shown in the desktop chat list)
    # ------------------------------------------------------------------

    @staticmethod
    def conversation_id(sender_id: str, channel_type: str) -> str:
        """Stable, non-reversible conversation id (never the phone number)."""
        import hashlib

        digest = hashlib.sha256(f"{channel_type}:{sender_id}".encode()).hexdigest()
        return f"{channel_type}-{digest[:16]}"

    @_db_locked
    def log_message(
        self,
        sender_id: str,
        channel_type: str,
        role: str,
        content: str,
        *,
        attachments: Optional[List[Dict[str, Any]]] = None,
        agent: str = "",
        model: str = "",
        delivery_status: str = "",
        delivery_error: str = "",
        message_handle: str = "",
    ) -> int:
        cur = self._db.execute(
            "INSERT INTO channel_messages (conversation_id, channel_type, role, "
            "content, attachments, agent, model, delivery_status, delivery_error, "
            "message_handle) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                self.conversation_id(sender_id, channel_type),
                channel_type,
                role,
                content,
                json.dumps(attachments or []),
                agent,
                model,
                delivery_status,
                delivery_error,
                message_handle,
            ),
        )
        self._db.commit()
        return int(cur.lastrowid)

    @_db_locked
    def backfill_logged_messages(self, channel_type: str = "sendblue") -> int:
        """Copy rolling histories into the durable log once (no timestamps
        existed, so they're stamped with the session's last update)."""
        added = 0
        rows = self._db.execute(
            "SELECT sender_id, conversation_history, updated_at FROM "
            "channel_sessions WHERE channel_type = ?",
            (channel_type,),
        ).fetchall()
        for row in rows:
            conv = self.conversation_id(row["sender_id"], channel_type)
            exists = self._db.execute(
                "SELECT 1 FROM channel_messages WHERE conversation_id = ? LIMIT 1",
                (conv,),
            ).fetchone()
            if exists:
                continue
            stamp = str(row["updated_at"]).replace(" ", "T") + "Z"
            for message in json.loads(row["conversation_history"] or "[]"):
                if message.get("role") not in ("user", "assistant"):
                    continue
                self._db.execute(
                    "INSERT INTO channel_messages (conversation_id, channel_type, "
                    "role, content, agent, created_at) VALUES (?,?,?,?,?,?)",
                    (
                        conv,
                        channel_type,
                        message["role"],
                        str(message.get("content", "")),
                        "Jarvis" if message["role"] == "assistant" else "",
                        stamp,
                    ),
                )
                added += 1
        self._db.commit()
        return added

    @_db_locked
    def update_delivery(self, message_id: int, status: str, error: str = "") -> None:
        self._db.execute(
            "UPDATE channel_messages SET delivery_status = ?, delivery_error = ? "
            "WHERE id = ?",
            (status, error, message_id),
        )
        self._db.commit()

    @_db_locked
    def logged_conversations(
        self, channel_type: str = "sendblue", limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Conversations with their last *limit* messages, oldest first."""
        conv_rows = self._db.execute(
            "SELECT conversation_id, MAX(created_at) AS updated_at, "
            "MIN(created_at) AS created_at FROM channel_messages "
            "WHERE channel_type = ? GROUP BY conversation_id "
            "ORDER BY updated_at DESC",
            (channel_type,),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for conv in conv_rows:
            rows = self._db.execute(
                "SELECT * FROM (SELECT * FROM channel_messages WHERE "
                "conversation_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (conv["conversation_id"], limit),
            ).fetchall()
            out.append(
                {
                    "id": conv["conversation_id"],
                    "channel": channel_type,
                    "created_at": conv["created_at"],
                    "updated_at": conv["updated_at"],
                    "messages": [
                        {
                            "id": f"{conv['conversation_id']}-{r['id']}",
                            "role": r["role"],
                            "content": r["content"],
                            "attachments": json.loads(r["attachments"] or "[]"),
                            "agent": r["agent"],
                            "model": r["model"],
                            "delivery_status": r["delivery_status"],
                            "delivery_error": r["delivery_error"],
                            "created_at": r["created_at"],
                        }
                        for r in rows
                    ],
                }
            )
        return out

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @_db_locked
    def get_or_create(self, sender_id: str, channel_type: str) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM channel_sessions WHERE sender_id = ? AND channel_type = ?",
            (sender_id, channel_type),
        ).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO channel_sessions (sender_id, channel_type) VALUES (?, ?)",
                (sender_id, channel_type),
            )
            self._db.commit()
            return {
                "sender_id": sender_id,
                "channel_type": channel_type,
                "conversation_history": [],
                "preferred_notification_channel": None,
                "pending_response": None,
            }
        return {
            "sender_id": row["sender_id"],
            "channel_type": row["channel_type"],
            "conversation_history": json.loads(row["conversation_history"]),
            "preferred_notification_channel": row["preferred_notification_channel"],
            "pending_response": row["pending_response"],
        }

    @_db_locked
    def append_message(
        self,
        sender_id: str,
        channel_type: str,
        role: str,
        content: str,
    ) -> None:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT conversation_history FROM channel_sessions "
                "WHERE sender_id = ? AND channel_type = ?",
                (sender_id, channel_type),
            ).fetchone()
            if row is None:
                self._db.rollback()
                return
            history: List[Dict[str, str]] = json.loads(row["conversation_history"])
            history.append({"role": role, "content": content})
            if len(history) > _MAX_HISTORY_TURNS:
                history = history[-_MAX_HISTORY_TURNS:]
            self._db.execute(
                "UPDATE channel_sessions "
                "SET conversation_history = ?, "
                "updated_at = datetime('now') "
                "WHERE sender_id = ? AND channel_type = ?",
                (json.dumps(history), sender_id, channel_type),
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    @_db_locked
    def recent_conversations(
        self, channel_type: str = "sendblue"
    ) -> List[Dict[str, Any]]:
        """Return recent exchanges without exposing sender IDs or credentials."""
        rows = self._db.execute(
            "SELECT conversation_history, updated_at FROM channel_sessions "
            "WHERE channel_type = ? AND conversation_history != '[]' "
            "ORDER BY updated_at DESC LIMIT 5",
            (channel_type,),
        ).fetchall()
        return [
            {
                "label": f"Phone conversation {index + 1}",
                "updated_at": row["updated_at"].replace(" ", "T") + "Z",
                "messages": [
                    {
                        "role": message.get("role"),
                        "content": str(message.get("content", ""))[:8000],
                    }
                    for message in json.loads(row["conversation_history"])[-20:]
                    if message.get("role") in ("user", "assistant")
                ],
            }
            for index, row in enumerate(rows)
        ]

    @_db_locked
    def set_notification_preference(
        self,
        sender_id: str,
        channel_type: str,
        preferred: str,
    ) -> None:
        self._db.execute(
            "UPDATE channel_sessions "
            "SET preferred_notification_channel = ?, "
            "updated_at = datetime('now') "
            "WHERE sender_id = ? AND channel_type = ?",
            (preferred, sender_id, channel_type),
        )
        self._db.commit()

    @_db_locked
    def set_pending_response(
        self,
        sender_id: str,
        channel_type: str,
        response: str,
    ) -> None:
        self._db.execute(
            "UPDATE channel_sessions "
            "SET pending_response = ?, "
            "updated_at = datetime('now') "
            "WHERE sender_id = ? AND channel_type = ?",
            (response, sender_id, channel_type),
        )
        self._db.commit()

    @_db_locked
    def clear_pending_response(self, sender_id: str, channel_type: str) -> None:
        self.set_pending_response(sender_id, channel_type, None)

    @_db_locked
    def expire_sessions(self, max_age_hours: int = 24) -> int:
        cur = self._db.execute(
            "UPDATE channel_sessions "
            "SET conversation_history = '[]', "
            "pending_response = NULL "
            "WHERE updated_at < datetime('now', ? || ' hours')",
            (f"-{max_age_hours}",),
        )
        self._db.commit()
        return cur.rowcount

    @_db_locked
    def get_last_active_channel(self, sender_id: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT channel_type FROM channel_sessions "
            "WHERE sender_id = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (sender_id,),
        ).fetchone()
        return row["channel_type"] if row else None

    @_db_locked
    def get_notification_targets(self) -> List[Dict[str, str]]:
        """Return all senders with a notification channel."""
        rows = self._db.execute(
            "SELECT sender_id, channel_type, "
            "preferred_notification_channel "
            "FROM channel_sessions "
            "WHERE preferred_notification_channel IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]

    @_db_locked
    def close(self) -> None:
        self._db.close()
