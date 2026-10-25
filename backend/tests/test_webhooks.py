"""
Razorpay webhooks (P7-5): only signed events count (HMAC-SHA256 of the raw
body with the webhook secret); retries are de-duplicated; a webhook and the
browser's Checkout report reach the same result, whichever arrives first.
"""
import hashlib
import hmac
import json

import pytest

import razorpay_client
from live_helpers import awaiting, create_order, customer_order, customer_report, failed, payment, report_failure, session

SECRET = "whsec_test_only"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(razorpay_client, "RAZORPAY_WEBHOOK_SECRET", SECRET)


def _event(name, pay):
    return {"entity": "event", "event": name, "contains": ["payment"],
            "payload": {"payment": {"entity": pay}}}


def post_event(client, event, secret=SECRET, event_id=None, body=None, signature=None):
    raw = body if body is not None else json.dumps(event).encode()
    sig = signature if signature is not None else hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}
    if event_id:
        headers["X-Razorpay-Event-Id"] = event_id
    return client.post("/api/webhooks/razorpay", content=raw, headers=headers)


def test_not_configured_is_503(client, monkeypatch):
    monkeypatch.setattr(razorpay_client, "RAZORPAY_WEBHOOK_SECRET", None)
    assert post_event(client, _event("payment.failed", failed())).status_code == 503


@pytest.mark.parametrize("case", ["wrong_secret", "tampered", "missing"])
def test_unsigned_or_tampered_events_are_rejected(client, case):
    create_order(client)
    event = _event("payment.failed", failed())
    raw = json.dumps(event).encode()
    if case == "wrong_secret":
        r = post_event(client, event, secret="not-the-secret")
    elif case == "tampered":
        good = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        r = post_event(client, event, body=raw.replace(b"1000", b"9999"), signature=good)
    else:
        r = post_event(client, event, signature="")
    assert r.status_code == 400
    assert session(client).json()["stage"] == "order_created"


def test_payment_failed_webhook_starts_the_recovery_without_the_browser(client):
    create_order(client)
    r = post_event(client, _event("payment.failed", failed()))
    assert r.json()["status"] == "failure_recorded"
    view = session(client).json()
    assert view["stage"] == "awaiting_customer"
    assert "(webhook)" in view["audit_trail"][0]["detail"]
    assert report_failure(client).status_code == 409          # the browser's report comes second


def test_captured_webhook_settles_the_recovery(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    r = post_event(client, _event("payment.captured", payment("pay_ok", "order_R1", "captured")))
    assert r.json()["status"] == "recovery_settled"
    assert session(client).json()["stage"] == "recovered"
    # Checkout's report arriving afterwards changes nothing.
    assert customer_report(client, token, payment("pay_ok", "order_R1", "captured")).status_code == 409


def test_webhook_after_checkout_report_is_acknowledged(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    assert customer_report(client, token, payment("pay_ok", "order_R1", "captured")).status_code == 200
    r = post_event(client, _event("payment.captured", payment("pay_ok", "order_R1", "captured")))
    assert r.status_code == 200 and r.json()["status"] == "already_recorded"


def test_failed_recovery_webhook_replans(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    post_event(client, _event("payment.failed", payment("pay_x", "order_R1", "failed")))
    view = session(client).json()
    assert view["recovery_attempts"] == 2
    assert view["recommended_action"] == "suggest_alternate_method"


def test_retried_event_is_processed_once(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    event = _event("payment.failed", payment("pay_x", "order_R1", "failed"))
    assert post_event(client, event, event_id="evt_1").json()["status"] == "recovery_settled"
    assert post_event(client, event, event_id="evt_1").json()["status"] == "duplicate"
    assert session(client).json()["recovery_attempts"] == 2      # not 3


def test_mismatched_payment_is_acknowledged_but_not_recorded(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    r = post_event(client, _event("payment.captured", payment("pay_ok", "order_R1", "captured", amount=99900)))
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert session(client).json()["stage"] == "awaiting_customer"


def test_events_for_other_orders_are_ignored(client):
    r = post_event(client, _event("payment.captured", payment("pay_z", "order_NotOurs", "captured")))
    assert r.json()["status"] == "ignored"
    assert post_event(client, {"event": "refund.created", "payload": {}}).json()["status"] == "ignored"
