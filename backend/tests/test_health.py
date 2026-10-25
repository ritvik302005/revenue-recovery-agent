"""
/api/health reports what the server actually knows (P5-9): key mode from
the prefix only, the storage backend, and the outcome of the latest real
Razorpay calls, recorded by the calls themselves. Live keys are refused.
The Razorpay SDK client is replaced; nothing here hits the network.
"""
from unittest.mock import MagicMock, patch

import pytest
import razorpay.errors

import razorpay_client
from razorpay_client import RazorpayNotConfigured


def _fake_client(order_create=None):
    client = MagicMock()
    client.order.create.side_effect = order_create or (lambda data: {"id": "order_H1", **data})
    return client


@pytest.fixture()
def test_keys(monkeypatch, isolated_state_db):
    for module in (razorpay_client, isolated_state_db):
        monkeypatch.setattr(module, "RAZORPAY_KEY_ID", "rzp_test_HealthCheck01")
    monkeypatch.setattr(razorpay_client, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(isolated_state_db, "RAZORPAY_KEY_SECRET", "secret")


def test_health_before_any_call(client, test_keys):
    body = client.get("/api/health").json()
    assert body["razorpay_keys_configured"] is True
    assert body["razorpay_key_mode"] == "test"
    assert body["storage_backend"] == "sqlite"
    assert body["razorpay_last_success_at"] is None and body["razorpay_last_failure_at"] is None


def test_health_never_contains_the_key(client, test_keys):
    assert "HealthCheck01" not in client.get("/api/health").text


def test_successful_call_is_recorded(client, test_keys):
    with patch("razorpay_client.razorpay.Client", return_value=_fake_client()):
        razorpay_client.create_real_order(amount=1000)
    body = client.get("/api/health").json()
    assert body["razorpay_last_success_at"] is not None
    assert body["razorpay_last_failure_at"] is None


@pytest.mark.parametrize("error,kind", [
    (razorpay.errors.BadRequestError("Authentication failed"), "rejected"),
    (ConnectionError("no route to host"), "unreachable_or_error"),
    (razorpay.errors.ServerError("boom"), "unreachable_or_error"),
])
def test_failed_call_is_recorded_with_its_kind_only(client, test_keys, error, kind):
    def fail(_data):
        raise error
    with patch("razorpay_client.razorpay.Client", return_value=_fake_client(fail)):
        with pytest.raises(type(error)):
            razorpay_client.create_real_order(amount=1000)
    body = client.get("/api/health").json()
    assert body["razorpay_last_failure_kind"] == kind
    assert body["razorpay_last_failure_at"] is not None
    assert str(error) not in client.get("/api/health").text


def test_missing_keys_are_not_a_razorpay_outcome(client, monkeypatch):
    monkeypatch.setattr(razorpay_client, "RAZORPAY_KEY_ID", None)
    with pytest.raises(RazorpayNotConfigured):
        razorpay_client.create_real_order(amount=1000)
    assert client.get("/api/health").json()["razorpay_last_failure_at"] is None


def test_live_keys_are_refused(client, monkeypatch, isolated_state_db):
    for module in (razorpay_client, isolated_state_db):
        monkeypatch.setattr(module, "RAZORPAY_KEY_ID", "rzp_live_SomethingReal")
    with patch("razorpay_client.razorpay.Client") as sdk:
        with pytest.raises(RazorpayNotConfigured):
            razorpay_client.create_real_order(amount=1000)
    sdk.assert_not_called()
    body = client.get("/api/health").json()
    assert body["razorpay_key_mode"] == "live"
    assert body["razorpay_keys_configured"] is False
    assert client.get("/api/live-demo/config").json()["configured"] is False
