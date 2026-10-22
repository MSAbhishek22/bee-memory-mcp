"""SQLite-backed memory store. Zero-config, single file, easy to inspect."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from .models import Alert, Conversation, Fact, Todo


class MemoryStore:
    def __init__(self, path: str | Path = ":memory:"):
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()  # RLock: public methods call each other; ALL db access is serialised through it (one shared sqlite connection is not safe for concurrent cursor use)
        self._init()

    def _init(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations(
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, started_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS facts(
                    id TEXT PRIMARY KEY, conversation_id TEXT, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS todos(
                    id TEXT PRIMARY KEY, conversation_id TEXT, payload TEXT NOT NULL, done INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS alerts(
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                """
            )

    # -- conversations -------------------------------------------------
    def add_conversation(self, conv: Conversation) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO conversations(id,payload,started_at) VALUES(?,?,?)",
                (conv.id, conv.model_dump_json(), conv.started_at.isoformat()),
            )

    def get_conversation(self, cid: str) -> Optional[Conversation]:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM conversations WHERE id=?", (cid,)).fetchone()
            return Conversation.model_validate_json(row["payload"]) if row else None

    def list_conversations(self, limit: int = 50) -> list[Conversation]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM conversations ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [Conversation.model_validate_json(r["payload"]) for r in rows]

    def search_conversations(self, query: str, limit: int = 10) -> list[Conversation]:
      with self._lock:
        q = f"%{query.lower()}%"
        rows = self._conn.execute(
            "SELECT payload FROM conversations WHERE lower(payload) LIKE ? ORDER BY started_at DESC LIMIT ?",
            (q, limit),
        ).fetchall()
        if rows:
            return [Conversation.model_validate_json(r["payload"]) for r in rows]
        # fall back to keyword overlap on transcript/title
        scored = []
        terms = {t.strip(".,?!") for t in query.lower().split() if len(t) > 3}
        for conv in self.list_conversations(100):
            hay = f"{conv.title} {conv.transcript}".lower()
            score = sum(1 for t in terms if t in hay)
            if score:
                scored.append((score, conv))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:limit]]

    # -- facts -----------------------------------------------------------
    def add_fact(self, fact: Fact) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO facts(id,conversation_id,payload) VALUES(?,?,?)",
                (fact.id, fact.conversation_id, fact.model_dump_json()),
            )

    def list_facts(self, limit: int = 100) -> list[Fact]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM facts LIMIT ?", (limit,)).fetchall()
            return [Fact.model_validate_json(r["payload"]) for r in rows]

    def search_facts(self, query: str, limit: int = 10) -> list[Fact]:
        with self._lock:
            terms = {t.strip(".,?!") for t in query.lower().split() if len(t) > 3}
            out = []
            for fact in self.list_facts(500):
                hay = fact.text.lower()
                if any(t in hay for t in terms) or query.lower() in hay:
                    out.append(fact)
            return out[:limit]

    # -- todos -----------------------------------------------------------
    def add_todo(self, todo: Todo) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO todos(id,conversation_id,payload,done) VALUES(?,?,?,?)",
                (todo.id, todo.conversation_id, todo.model_dump_json(), int(todo.done)),
            )

    def list_todos(self, include_done: bool = False) -> list[Todo]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM todos").fetchall()
            todos = [Todo.model_validate_json(r["payload"]) for r in rows]
            return todos if include_done else [t for t in todos if not t.done]

    def mark_todo_done(self, todo_id: str) -> Optional[Todo]:
        with self._lock:
            todo = next((t for t in self.list_todos(include_done=True) if t.id == todo_id), None)
            if todo:
                todo.done = True
                self.add_todo(todo)
            return todo

    # -- alerts ----------------------------------------------------------
    def add_alert(self, alert: Alert) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO alerts(id,payload,created_at) VALUES(?,?,?)",
                (alert.id, alert.model_dump_json(), alert.created_at.isoformat()),
            )

    def list_alerts(self, limit: int = 20) -> list[Alert]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [Alert.model_validate_json(r["payload"]) for r in rows]

    def counts(self) -> dict:
        with self._lock:
            return {
                "conversations": self._conn.execute("SELECT COUNT(*) c FROM conversations").fetchone()["c"],
                "facts": self._conn.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"],
                "todos_open": len(self.list_todos()),
                "alerts": self._conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"],
            }
