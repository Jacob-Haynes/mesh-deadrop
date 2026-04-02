"""SQLite message store for the dead drop."""

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class MessageStore:
    """Thread-safe SQLite store for dead drop messages and node tracking."""

    def __init__(self, db_path: str = "/opt/mesh-deadrop/messages.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    body TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    delivered INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    callsign TEXT PRIMARY KEY,
                    last_seen TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0
                );
            """)
            self._conn.commit()

    def store_message(self, sender: str, recipient: str, body: str) -> int:
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (sender, recipient, body, timestamp) VALUES (?, ?, ?, ?)",
                (sender, recipient, body, ts),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_messages(self, recipient: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, sender, recipient, body, timestamp FROM messages "
                "WHERE recipient = ? COLLATE NOCASE AND delivered = 0 ORDER BY id",
                (recipient,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_delivered(self, msg_id: int):
        with self._lock:
            self._conn.execute(
                "UPDATE messages SET delivered = 1 WHERE id = ?", (msg_id,)
            )
            self._conn.commit()

    def pending_count(self, recipient: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient = ? COLLATE NOCASE AND delivered = 0",
                (recipient,),
            ).fetchone()
            return row[0]

    def get_stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            delivered = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE delivered = 1"
            ).fetchone()[0]
            nodes = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            return {
                "total": total,
                "delivered": delivered,
                "pending": total - delivered,
                "nodes": nodes,
            }

    def get_node_list(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT callsign, last_seen, message_count FROM nodes ORDER BY last_seen DESC"
            ).fetchall()
            result = []
            for r in rows:
                pending = self._conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE recipient = ? COLLATE NOCASE AND delivered = 0",
                    (r["callsign"],),
                ).fetchone()[0]
                result.append({
                    "callsign": r["callsign"],
                    "last_seen": r["last_seen"],
                    "message_count": r["message_count"],
                    "pending": pending,
                })
            return result

    def get_recent_messages(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, sender, recipient, timestamp, delivered FROM messages "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_node(self, callsign: str):
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO nodes (callsign, last_seen, message_count) VALUES (?, ?, 1) "
                "ON CONFLICT(callsign) DO UPDATE SET last_seen = ?, message_count = message_count + 1",
                (callsign, ts, ts),
            )
            self._conn.commit()