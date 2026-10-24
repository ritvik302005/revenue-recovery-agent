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

Two atomic operations sit on top of it, for state that must not race:
- set_if_absent(): write only if the key doesn't exist yet (used to
  register a payment id as used, exactly once).
- update_atomic(): read, check and write one key under a lock, so two
  requests can't both pass the same stage check (live-demo sessions).
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


def _sqlite_conn(autocommit: bool = False) -> sqlite3.Connection:
    # autocommit=True leaves transactions to the caller (BEGIN IMMEDIATE
    # in the atomic operations below); the default keeps sqlite3's
    # implicit transactions for the simple get/set/delete calls.
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None if autocommit else "")
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


def _live_row(conn: sqlite3.Connection, key: str) -> Optional[dict]:
    """Current value for `key` inside an open transaction, None if missing or expired."""
    row = conn.execute("SELECT value, expires_at FROM kv_store WHERE key = ?", (key,)).fetchone()
    if row is None or (row[1] is not None and row[1] < time.time()):
        return None
    return json.loads(row[0])


def set_if_absent(key: str, value: dict, ttl_seconds: Optional[int] = None) -> bool:
    """Store `value` only if `key` doesn't already exist (or has expired).
    Returns True if this call wrote it, False if the key was already taken."""
    payload = json.dumps(value)
    if _redis_client:
        return bool(_redis_client.set(key, payload, nx=True, ex=ttl_seconds))

    expires_at = (time.time() + ttl_seconds) if ttl_seconds else None
    conn = _sqlite_conn(autocommit=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if _live_row(conn, key) is not None:
            conn.execute("ROLLBACK")
            return False
        conn.execute(
            "INSERT OR REPLACE INTO kv_store (key, value, expires_at) VALUES (?, ?, ?)",
            (key, payload, expires_at),
        )
        conn.execute("COMMIT")
        return True
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def update_atomic(key: str, fn, ttl_seconds: Optional[int] = None) -> dict:
    """Read-modify-write `key` with no other writer in between.

    `fn(current)` receives the stored dict (or None) and returns the new
    dict to store. It may raise to abort: nothing is written and the
    exception reaches the caller. Returns the dict that was stored."""
    if _redis_client:
        import redis
        with _redis_client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    new = fn(json.loads(raw) if raw is not None else None)
                    pipe.multi()
                    if ttl_seconds:
                        pipe.setex(key, ttl_seconds, json.dumps(new))
                    else:
                        pipe.set(key, json.dumps(new))
                    pipe.execute()
                    return new
                except redis.WatchError:
                    continue  # another writer got there first; re-read and retry

    expires_at = (time.time() + ttl_seconds) if ttl_seconds else None
    conn = _sqlite_conn(autocommit=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        new = fn(_live_row(conn, key))
        conn.execute(
            "INSERT OR REPLACE INTO kv_store (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(new), expires_at),
        )
        conn.execute("COMMIT")
        return new
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
