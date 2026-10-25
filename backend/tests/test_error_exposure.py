"""
What the browser and the logs get to see when something fails: Razorpay's
own error description is passed through, raw exception text is not, and
REDIS_URL credentials never reach a log line. Razorpay is mocked.
"""
from unittest.mock import patch

import pytest
import razorpay.errors
import requests

from razorpay_client import RazorpayNotConfigured

INTERNAL = "connect to 10.0.0.7:443 failed, pool=internal-pool-3"


def _create_order_failing_with(client, exc):
    with patch("main.create_real_order", side_effect=exc):
        return client.post("/api/live-demo/create-order", json={"amount": 1000})


def test_razorpay_description_is_passed_through(client):
    r = _create_order_failing_with(client, razorpay.errors.BadRequestError("The amount must be at least INR 1.00"))
    assert r.status_code == 502
    assert "Razorpay said: The amount must be at least INR 1.00" in r.json()["detail"]


def test_network_error_text_is_not_returned(client):
    r = _create_order_failing_with(client, requests.exceptions.ConnectionError(INTERNAL))
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "unreachable or returned an error" in detail
    assert "10.0.0.7" not in detail and "internal-pool" not in detail


def test_server_error_text_is_not_returned(client):
    r = _create_order_failing_with(client, razorpay.errors.ServerError(INTERNAL))
    assert r.status_code == 502
    assert "10.0.0.7" not in r.json()["detail"]


def test_missing_keys_is_503_without_setup_instructions(client):
    r = _create_order_failing_with(client, RazorpayNotConfigured("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set"))
    assert r.status_code == 503
    assert "RAZORPAY_KEY" not in r.json()["detail"]


def test_fetch_payment_errors_are_mapped_too(client):
    with patch("main.create_real_order", return_value={"id": "order_A", "amount": 1000, "currency": "INR"}):
        client.post("/api/live-demo/create-order", json={"amount": 1000})
    with patch("main.fetch_real_payment", side_effect=requests.exceptions.Timeout(INTERNAL)):
        r = client.post("/api/live-demo/report-failure", params={"order_id": "order_A", "payment_id": "pay_x"})
    assert r.status_code == 502
    assert "10.0.0.7" not in r.json()["detail"]


def test_redis_url_is_redacted():
    import storage
    assert storage._redacted("rediss://default:s3cretPass@eu1-fancy-cat.upstash.io:6379/0") == \
        "rediss://eu1-fancy-cat.upstash.io:6379"
    assert "s3cret" not in storage._redacted("redis://:s3cret@localhost")


@pytest.mark.parametrize("value", [
    # what happened in production: the whole redis-cli command pasted as REDIS_URL
    "redis-cli --tls -u rediss://default:s3cretPass@eu1-fancy-cat.upstash.io:6379",
    " rediss://default:s3cretPass@host.upstash.io:6379 extra",
    "https://default:s3cretPass@host.upstash.io",
    "default:s3cretPass@host.upstash.io:6379",
    "rediss://default:s3cretPass@host.upstash.io:notaport",
])
def test_anything_but_a_clean_redis_url_is_never_echoed(value):
    import storage
    out = storage._redacted(value)
    assert "s3cret" not in out and "default" not in out and "upstash" not in out


def test_redis_failure_log_has_no_credentials(tmp_path, monkeypatch, capsys):
    import importlib
    import storage
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "s.db"))
    # Port 1 refuses immediately, so this falls back to SQLite without waiting.
    monkeypatch.setenv("REDIS_URL", "redis://default:s3cretPass@127.0.0.1:1/0")
    try:
        importlib.reload(storage)
        out = capsys.readouterr().out
        assert "falling back to SQLite" in out
        assert "127.0.0.1:1" in out
        assert "s3cretPass" not in out and "default:" not in out
    finally:
        monkeypatch.delenv("REDIS_URL")
        importlib.reload(storage)
