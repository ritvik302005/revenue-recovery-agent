"""
Persistence layer for server state that previously lived in plain
Python dicts (`_last_results`, `_live_demo_store` in main.py). Those
disappeared on every restart and were unsafe with more than one
server process/instance.

Backend selection:
- If REDIS_URL is set (and the `redis` package is installed and
  reachable), state is stored in Redis. This is the recommended
  setup for anything beyond a single local process — TTLs are native,
  and multiple app instances share the same store.
- Otherwise, falls back to a local SQLite file (state.db next to this
  file). Single-instance only, but state now survives a restart,
  which the old in-memory dicts never did.

Usage is a tiny key/value API — set_value / get_value / delete_value —
with values as plain JSON-serializable dicts, and an optional
ttl_seconds for entries that should expire (e.g. live-demo sessions).
"""
import json
import os
import sqlite3
import time
from typing import Optional

REDIS_URL = os.environ.get("REDIS_URL")
LIVE_DEMO_TTL_SECONDS = int(os.environ.get("LIVE_DEMO_TTL_SECONDS", 3600))  # 1 hour
DB_PATH = os.environ.get("SQLITE_PATH", os.path.join(os.path.dirname(__file__), "state.db"))

_redis_client = None
if REDIS_URL:
    try:
        import redis  # optional dependency — only needed if REDIS_URL is set
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        print(f"[storage] Connected to Redis at {REDIS_URL}.")
    except Exception as e:
        print(f"[storage] Could not connect to Redis ({e}); falling back to SQLite at {DB_PATH}.")
        _redis_client = None


def _sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at REAL
        )
        """
    )
    return conn


def set_value(key: str, value: dict, ttl_seconds: Optional[int] = None) -> None:
    """Store a JSON-serializable dict under `key`, with an optional
    expiry in seconds (used for live-demo sessions)."""
    payload = json.dumps(value)
    if _redis_client:
        if ttl_seconds:
            _redis_client.setex(key, ttl_seconds, payload)
        else:
            _redis_client.set(key, payload)
        return

    expires_at = (time.time() + ttl_seconds) if ttl_seconds else None
    with _sqlite_conn() as conn:
        conn.execute(
            "INSERT INTO kv_store (key, value, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
            (key, payload, expires_at),
        )


def get_value(key: str) -> Optional[dict]:
    """Return the stored dict for `key`, or None if missing/expired."""
    if _redis_client:
        raw = _redis_client.get(key)
        return json.loads(raw) if raw is not None else None

    with _sqlite_conn() as conn:
        row = conn.execute(
            "SELECT value, expires_at FROM kv_store WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at is not None and expires_at < time.time():
            conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            return None
        return json.loads(value)


def delete_value(key: str) -> None:
    if _redis_client:
        _redis_client.delete(key)
        return
    with _sqlite_conn() as conn:
        conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
