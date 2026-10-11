"""Persistent analysis history (SQLite, stdlib only).

Every completed analysis is stored with its input and full result so the
user can reopen it later from the History tab. Single-user local app, so
there is no per-user separation.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "history.db"
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY, created REAL NOT NULL, title TEXT NOT NULL,
        status TEXT, domain TEXT, mode TEXT, n_requirements INTEGER, n_questions INTEGER,
        input TEXT NOT NULL, result TEXT NOT NULL)""")
    return c


def _title(text: str) -> str:
    words = " ".join(text.split()).split(" ")
    t = " ".join(words[:10])
    return t + ("…" if len(words) > 10 else "")


def save(text: str, mode: str, result: dict) -> str:
    hid = uuid.uuid4().hex[:12]
    q = result.get("quality") or {}
    with _lock, _conn() as c:
        c.execute("INSERT INTO history VALUES (?,?,?,?,?,?,?,?,?,?)", (
            hid, time.time(), _title(text), result.get("status"),
            (result.get("gate") or {}).get("domain", ""), mode,
            q.get("requirements"), q.get("open_questions"),
            text, json.dumps(result, ensure_ascii=False)))
    return hid


def list_items(limit: int = 100) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("""SELECT id, created, title, status, domain, mode, n_requirements, n_questions
                            FROM history ORDER BY created DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get(hid: str) -> dict | None:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM history WHERE id = ?", (hid,)).fetchone()
    if not r:
        return None
    out = dict(r)
    out["result"] = json.loads(out["result"])
    return out


def delete(hid: str) -> bool:
    with _lock, _conn() as c:
        return c.execute("DELETE FROM history WHERE id = ?", (hid,)).rowcount > 0


def clear() -> int:
    with _lock, _conn() as c:
        return c.execute("DELETE FROM history").rowcount
