"""
Who may call the endpoints that reach Razorpay, and how often (P5-1, P5-2).

A browser can't keep a static API key secret, so instead:
- POST /api/session issues a short-lived random token, sent back in the
  X-Session-Token header. Each token carries a small budget of real
  Razorpay orders, and a live-demo session belongs to the token that
  created it.
- A daily cap bounds real order creation for the whole server, however
  many tokens are issued.
- Rate limits are per client IP and counted in the shared store (SQLite,
  or Redis when configured), so they hold across workers and restarts.
  Behind a proxy the client IP comes from X-Forwarded-For, trusting only
  the last TRUSTED_PROXY_HOPS entries (the ones our own proxies added).

Only a hash of each token is stored. A bot check (e.g. Turnstile) can
later gate POST /api/session without changing anything else.
"""
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import Header, HTTPException, Request

import storage

SESSION_TTL_SECONDS = int(os.environ.get("ACCESS_SESSION_TTL_SECONDS", 1800))   # 30 min
# One live demo uses up to 4 orders (the original + 3 recovery attempts),
# and a batch with live orders up to MAX_LIVE_ORDERS_PER_BATCH (5).
ORDERS_PER_SESSION = int(os.environ.get("ORDERS_PER_SESSION", 10))
MAX_LIVE_ORDERS_PER_DAY = int(os.environ.get("MAX_LIVE_ORDERS_PER_DAY", 200))
TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", 0))

SESSION_KEY_PREFIX = "access:"
DAILY_KEY_PREFIX = "cap:live_orders:"


def client_ip(request: Request) -> str:
    if TRUSTED_PROXY_HOPS > 0:
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if len(hops) >= TRUSTED_PROXY_HOPS:
            # Entries further left were sent by the client and can be forged.
            return hops[-TRUSTED_PROXY_HOPS]
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, max_requests: int, window_seconds: int = 60):
    """A FastAPI dependency: at most `max_requests` per client IP per window."""
    def dependency(request: Request) -> None:
        window = int(time.time() // window_seconds)
        key = f"ratelimit:{scope}:{client_ip(request)}:{window}"

        def bump(current: Optional[dict]) -> dict:
            count = (current or {}).get("count", 0)
            if count >= max_requests:
                raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
            return {"count": count + 1}

        storage.update_atomic(key, bump, ttl_seconds=window_seconds * 2)
    return dependency


def owner_of(token: str) -> str:
    """Stable id for a token, safe to store and compare."""
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session() -> dict:
    storage.purge_expired()   # cheap housekeeping; this endpoint is rate limited
    token = secrets.token_urlsafe(32)
    storage.set_value(SESSION_KEY_PREFIX + owner_of(token),
                      {"orders_left": ORDERS_PER_SESSION, "expires_at": time.time() + SESSION_TTL_SECONDS},
                      ttl_seconds=SESSION_TTL_SECONDS)
    return {"token": token, "expires_in": SESSION_TTL_SECONDS, "orders_per_session": ORDERS_PER_SESSION}


def require_session(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")) -> str:
    """A FastAPI dependency: returns the caller's token, or 401."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="This needs a session. Reload the page and try again.")
    record = storage.get_value(SESSION_KEY_PREFIX + owner_of(x_session_token))
    if not record or record.get("expires_at", 0) < time.time():
        raise HTTPException(status_code=401, detail="Your session has expired. Reload the page to start a new one.")
    return x_session_token


def _day_key() -> str:
    return DAILY_KEY_PREFIX + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _session_take(token: str, wanted: int) -> int:
    """Atomically take up to `wanted` from the session budget (negative gives back)."""
    return _owner_take(owner_of(token), wanted)


def _owner_take(owner: str, wanted: int) -> int:
    key = SESSION_KEY_PREFIX + owner
    granted = 0

    def fn(current: Optional[dict]) -> dict:
        nonlocal granted
        if current is None:     # expired between require_session and now
            raise HTTPException(status_code=401, detail="Your session has expired. Reload the page to start a new one.")
        granted = min(wanted, current.get("orders_left", 0))
        return {**current, "orders_left": current.get("orders_left", 0) - granted}

    session = storage.get_value(key) or {}
    ttl = max(1, int(session.get("expires_at", 0) - time.time()))
    storage.update_atomic(key, fn, ttl_seconds=ttl)
    return granted


def _day_take(wanted: int) -> int:
    """Atomically take up to `wanted` from today's server-wide cap (negative gives back)."""
    granted = 0

    def fn(current: Optional[dict]) -> dict:
        nonlocal granted
        used = (current or {}).get("used", 0)
        granted = min(wanted, MAX_LIVE_ORDERS_PER_DAY - used)
        return {"used": max(0, used + granted)}

    storage.update_atomic(_day_key(), fn, ttl_seconds=2 * 86400)
    return granted


def reserve_orders(token: str, wanted: int) -> int:
    """Take up to `wanted` real-order slots from this session's budget and
    from today's server-wide cap. Returns the number granted (maybe 0)."""
    return reserve_orders_for_owner(owner_of(token), wanted)


def reserve_orders_for_owner(owner: str, wanted: int) -> int:
    """As reserve_orders, for a session known only by its owner id (e.g. a
    customer paying a recovery request the session's demo created)."""
    from_session = max(0, _owner_take(owner, wanted))
    if from_session == 0:
        return 0
    from_day = max(0, _day_take(from_session))
    if from_day < from_session:   # give back what today's cap couldn't cover
        _owner_take(owner, -(from_session - from_day))
    return from_day


def require_orders(token: str, wanted: int = 1) -> None:
    """Reserve exactly `wanted` slots or raise 429 (nothing is kept on failure)."""
    require_orders_for_owner(owner_of(token), wanted)


def require_orders_for_owner(owner: str, wanted: int = 1) -> None:
    granted = reserve_orders_for_owner(owner, wanted)
    if granted < wanted:
        if granted:
            refund_orders_for_owner(owner, granted)
        raise HTTPException(
            status_code=429,
            detail="The limit on real Razorpay test orders has been reached for this session or for today. "
                   "Reload the page for a new session, or try again tomorrow.",
        )


def refund_orders(token: str, n: int) -> None:
    """Return `n` slots, e.g. when the Razorpay call failed and no order exists."""
    refund_orders_for_owner(owner_of(token), n)


def refund_orders_for_owner(owner: str, n: int) -> None:
    if n <= 0:
        return
    _day_take(-n)
    try:
        _owner_take(owner, -n)
    except HTTPException:
        pass    # session already expired; nothing to give back to
