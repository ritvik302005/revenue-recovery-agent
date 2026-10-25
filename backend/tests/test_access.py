"""
Access model (P5-1) and rate limits (P5-2): session tokens, ownership of
live-demo sessions, the per-session and daily caps on real orders, and
proxy-aware per-IP limits in the shared store. Razorpay is mocked.
"""
import time
from unittest.mock import patch

import pytest

import access
from conftest import new_session_client

ACTING = [
    ("post", "/api/live-demo/create-order", {"json": {"amount": 1000}}),
    ("post", "/api/live-demo/report-failure", {"params": {"order_id": "order_A", "payment_id": "pay_x"}}),
    ("post", "/api/live-demo/create-recovery-order", {"params": {"order_id": "order_A"}}),
    ("post", "/api/live-demo/report-recovery",
     {"params": {"order_id": "order_A", "recovery_order_id": "order_R", "recovery_payment_id": "pay_x"}}),
    ("post", "/api/batch/run", {"params": {"n": 5}}),
]


def _orders():
    """A create_real_order stand-in that hands out distinct order ids."""
    n = iter(range(1, 1000))
    return lambda amount, receipt=None, **_: {"id": f"order_T{next(n)}", "amount": amount, "currency": "INR"}


@pytest.mark.parametrize("method,path,kwargs", ACTING)
def test_acting_endpoints_need_a_session(anon_client, method, path, kwargs):
    with patch("main.create_real_order") as order, patch("main.fetch_real_payment") as fetch:
        r = getattr(anon_client, method)(path, **kwargs)
    assert r.status_code == 401
    order.assert_not_called()
    fetch.assert_not_called()


def test_unknown_token_is_rejected(anon_client):
    r = anon_client.post("/api/batch/run", params={"n": 5}, headers={"X-Session-Token": "made-up"})
    assert r.status_code == 401


def test_expired_token_is_rejected(client, isolated_state_db):
    key = access.SESSION_KEY_PREFIX + access.owner_of(client.headers["X-Session-Token"])
    record = isolated_state_db.storage.get_value(key)
    isolated_state_db.storage.set_value(key, {**record, "expires_at": time.time() - 1}, ttl_seconds=60)
    r = client.post("/api/batch/run", params={"n": 5})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"]


def test_read_only_endpoints_stay_open(anon_client):
    assert anon_client.get("/api/health").status_code == 200
    assert anon_client.get("/api/showcase/case").status_code == 200
    assert anon_client.get("/api/live-demo/config").status_code == 200


def test_only_the_hash_of_a_token_is_stored(client, isolated_state_db):
    token = client.headers["X-Session-Token"]
    assert isolated_state_db.storage.get_value(access.SESSION_KEY_PREFIX + token) is None
    assert isolated_state_db.storage.get_value(access.SESSION_KEY_PREFIX + access.owner_of(token)) is not None


def test_another_session_cannot_drive_my_demo(client, isolated_state_db):
    with patch("main.create_real_order", side_effect=_orders()):
        order_id = client.post("/api/live-demo/create-order", json={"amount": 1000}).json()["id"]
    intruder = new_session_client(isolated_state_db)
    with patch("main.fetch_real_payment") as fetch:
        r = intruder.post("/api/live-demo/report-failure", params={"order_id": order_id, "payment_id": "pay_x"})
    assert r.status_code == 403
    fetch.assert_not_called()


def test_session_order_budget(isolated_state_db, monkeypatch):
    monkeypatch.setattr(access, "ORDERS_PER_SESSION", 2)
    c = new_session_client(isolated_state_db)
    with patch("main.create_real_order", side_effect=_orders()) as order:
        codes = [c.post("/api/live-demo/create-order", json={"amount": 1000}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert order.call_count == 2


def test_daily_cap_holds_across_sessions(isolated_state_db, monkeypatch):
    monkeypatch.setattr(access, "MAX_LIVE_ORDERS_PER_DAY", 2)
    first, second = new_session_client(isolated_state_db), new_session_client(isolated_state_db)
    with patch("main.create_real_order", side_effect=_orders()) as order:
        codes = [first.post("/api/live-demo/create-order", json={"amount": 1000}).status_code,
                 second.post("/api/live-demo/create-order", json={"amount": 1000}).status_code,
                 second.post("/api/live-demo/create-order", json={"amount": 1000}).status_code]
    assert codes == [200, 200, 429]
    assert order.call_count == 2


def test_failed_razorpay_call_gives_the_slot_back(isolated_state_db, monkeypatch):
    monkeypatch.setattr(access, "ORDERS_PER_SESSION", 1)
    c = new_session_client(isolated_state_db)
    with patch("main.create_real_order", side_effect=ConnectionError("down")):
        assert c.post("/api/live-demo/create-order", json={"amount": 1000}).status_code == 502
    with patch("main.create_real_order", side_effect=_orders()):
        assert c.post("/api/live-demo/create-order", json={"amount": 1000}).status_code == 200


def test_batch_live_orders_use_the_session_budget(isolated_state_db, monkeypatch):
    monkeypatch.setattr(access, "ORDERS_PER_SESSION", 3)
    c = new_session_client(isolated_state_db)
    with patch("simulate_batch.create_real_order", side_effect=_orders()) as order:
        first = c.post("/api/batch/run", params={"n": 12, "try_live_orders": True}).json()
        second = c.post("/api/batch/run", params={"n": 12, "try_live_orders": True}).json()
    real = lambda run: sum(r["razorpay_source"] == "razorpay_test_order" for r in run["results"])
    assert real(first) == 3       # budget 3 < MAX_LIVE_ORDERS_PER_BATCH 5
    assert real(second) == 0      # budget used up; the batch still runs on local ids
    assert second["count"] == 12
    assert order.call_count == 3


@pytest.fixture()
def frozen_window():
    """Keep the rate-limit tests inside one window (no flake at a minute boundary)."""
    with patch("access.time.time", return_value=time.time()):
        yield


@pytest.mark.usefixtures("frozen_window")
def test_rate_limit_per_ip(anon_client):
    codes = [anon_client.post("/api/session").status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


@pytest.mark.usefixtures("frozen_window")
def test_forwarded_for_is_ignored_without_trusted_proxies(anon_client, monkeypatch):
    monkeypatch.setattr(access, "TRUSTED_PROXY_HOPS", 0)
    codes = [anon_client.post("/api/session", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
             for i in range(11)]
    assert codes[10] == 429       # a spoofed header doesn't buy a fresh bucket


@pytest.mark.usefixtures("frozen_window")
def test_forwarded_for_behind_one_trusted_proxy(anon_client, monkeypatch):
    monkeypatch.setattr(access, "TRUSTED_PROXY_HOPS", 1)
    # The client forges the left entry; our proxy appended the real IP on the right.
    for _ in range(10):
        anon_client.post("/api/session", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9"})
    assert anon_client.post("/api/session", headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.9"}).status_code == 429
    assert anon_client.post("/api/session", headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 200


def test_purge_expired_drops_old_rows(isolated_state_db):
    storage = isolated_state_db.storage
    storage.set_value("old", {"x": 1}, ttl_seconds=1)
    storage.set_value("keep", {"x": 1})
    with patch("storage.time.time", return_value=time.time() + 5):
        storage.purge_expired()
    with storage._sqlite_conn() as conn:
        keys = {k for (k,) in conn.execute("SELECT key FROM kv_store")}
    assert "old" not in keys and "keep" in keys
