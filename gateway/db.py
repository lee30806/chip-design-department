"""게이트웨이 저장소 (SQLite). 사용자, 세션, API 키, 승인 기록, SPEC 작업 공간, 실행 대응, 판정, 감사 기록."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY, display TEXT NOT NULL, roles TEXT NOT NULL, caps TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'human', seat TEXT, pw_hash TEXT, created TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS api_keys (key_hash TEXT PRIMARY KEY, username TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, target TEXT NOT NULL, decision TEXT NOT NULL,
  by TEXT NOT NULL, roles TEXT NOT NULL, at TEXT NOT NULL, spec_sha TEXT, run_id TEXT, reqs TEXT, note TEXT, extra TEXT);
CREATE TABLE IF NOT EXISTS specs (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, source_kind TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL,
  created TEXT NOT NULL, frozen_sha TEXT, freeze_requested_sha TEXT);
CREATE TABLE IF NOT EXISTS spec_versions (spec_id TEXT NOT NULL, sha TEXT NOT NULL, markdown TEXT NOT NULL, by TEXT NOT NULL,
  at TEXT NOT NULL, note TEXT, PRIMARY KEY (spec_id, sha));
CREATE TABLE IF NOT EXISTS spec_figures (spec_id TEXT NOT NULL, n INTEGER NOT NULL, page INTEGER, caption TEXT, bbox TEXT,
  wavejson TEXT, PRIMARY KEY (spec_id, n));
CREATE TABLE IF NOT EXISTS spec_answers (spec_id TEXT NOT NULL, qkey TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
  by TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (spec_id, qkey));
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, spec_id TEXT, spec_sha TEXT, by TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signoffs (run_id TEXT NOT NULL, kind TEXT NOT NULL, decision TEXT NOT NULL, by TEXT NOT NULL,
  at TEXT NOT NULL, note TEXT, PRIMARY KEY (run_id, kind));
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, username TEXT, action TEXT NOT NULL,
  detail TEXT);
"""


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            return cur.lastrowid

    def audit(self, username: str | None, action: str, detail: dict | None = None) -> None:
        self.x("INSERT INTO audit (at, username, action, detail) VALUES (?,?,?,?)",
               (now(), username, action, json.dumps(detail or {}, ensure_ascii=False)))
