"""
The Redis branch of storage.py (P5-14), which the deployment will use:
TTLs, atomic read-modify-write under contention, and the app's flows on
top of it. Runs against fakeredis (an in-memory Redis), so no server is needed.
"""
import threading
from unittest.mock import patch

import fakeredis
import pytest
from fastapi import HTTPException

from conftest import new_session_client


@pytest.fixture()
def redis_main(isolated_state_db):
    main = isolated_state_db
    with patch.object(main.storage, "_redis_client", fakeredis.FakeRedis(decode_responses=True)):
        yield main


def test_backend_is_reported(redis_main):
    assert redis_main.storage.backend_name() == "redis"
    assert new_session_client(redis_main).get("/api/health").json()["storage_backend"] == "redis"


def test_set_get_delete_and_ttl(redis_main):
    storage = redis_main.storage
    storage.set_value("k", {"a": 1}, ttl_seconds=60)
    assert storage.get_value("k") == {"a": 1}
    assert 0 < storage._redis_client.ttl("k") <= 60
    storage.set_value("forever", {"b": 2})
    assert storage._redis_client.ttl("forever") == -1
    storage.delete_value("k")
    assert storage.get_value("k") is None
    storage.purge_expired()   # a no-op on Redis; must not fail


def test_update_atomic_under_contention(redis_main):
    storage = redis_main.storage
    storage.set_value("counter", {"n": 0})
    barrier = threading.Barrier(16)

    def bump():
        barrier.wait(timeout=5)
        storage.update_atomic("counter", lambda cur: {"n": cur["n"] + 1})

    threads = [threading.Thread(target=bump) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert storage.get_value("counter") == {"n": 16}


def test_update_atomic_abort_writes_nothing(redis_main):
    storage = redis_main.storage
    storage.set_value("k", {"stage": "a"})

    def refuse(_cur):
        raise HTTPException(status_code=409, detail="no")

    with pytest.raises(HTTPException):
        storage.update_atomic("k", refuse)
    assert storage.get_value("k") == {"stage": "a"}


def test_live_demo_and_budgets_work_on_redis(redis_main, monkeypatch):
    import access
    monkeypatch.setattr(access, "ORDERS_PER_SESSION", 1)
    c = new_session_client(redis_main)
    order = {"id": "order_Rd1", "amount": 1000, "currency": "INR"}
    with patch("main.create_real_order", return_value=order):
        assert c.post("/api/live-demo/create-order", json={"amount": 1000}).status_code == 200
        assert c.post("/api/live-demo/create-order", json={"amount": 1000}).status_code == 429
    failed = {"id": "pay_Rd1", "order_id": "order_Rd1", "amount": 1000, "currency": "INR",
              "status": "failed", "error_code": "BAD_REQUEST_ERROR", "error_reason": "payment_timed_out"}
    with patch("main.fetch_real_payment", return_value=failed):
        r = c.post("/api/live-demo/report-failure", params={"order_id": "order_Rd1", "payment_id": "pay_Rd1"})
        replay = c.post("/api/live-demo/report-failure", params={"order_id": "order_Rd1", "payment_id": "pay_Rd1"})
    assert r.status_code == 200 and replay.status_code == 409
    assert redis_main.storage._redis_client.ttl("live_demo:order_Rd1") > 0


def test_rate_limit_counts_in_redis(redis_main):
    from fastapi.testclient import TestClient
    anon = TestClient(redis_main.app)
    with patch("access.time.time", return_value=1_800_000_000.0):
        codes = [anon.post("/api/session").status_code for _ in range(11)]
    assert codes[10] == 429
    assert any(k.startswith("ratelimit:session:") for k in redis_main.storage._redis_client.keys("*"))
