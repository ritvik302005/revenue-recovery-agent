"""
Live demo (P1 guarantees, P7 flow): a real failure is executed at once; the
customer pays on a server-bound recovery request; stages only move forward;
payments can't be reused, replayed, raced or faked. Razorpay is mocked.
"""
import threading
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from conftest import sign
from live_helpers import (awaiting, create_order, customer_order, customer_report, failed, pay_request,
                          payment, report_failure, session, token_of)


# ---- the agent executes its decision at once (P7-1) ---------------------------

def test_failure_is_executed_immediately(client):
    create_order(client)
    view = report_failure(client).json()
    assert view["failure_reason"] == "bank_timeout"
    assert view["recommended_action"] == "retry_same_method"
    assert view["stage"] == "awaiting_customer"
    assert view["recovery_attempts"] == 1
    req = view["current_request"]
    assert req["status"] == "open" and req["seconds_until_available"] == 0 and req["excluded_method"] is None
    assert len(view["outbox"]) == 1 and view["outbox"][0]["link"] == req["link"]
    assert "try again" in view["outbox"][0]["text"]
    assert [e["step"] for e in view["audit_trail"]] == ["classify", "select_action", "safety_check", "execute"]


def test_real_test_card_failure_gets_a_link_with_card_hidden(client):
    """What Razorpay test mode really returns for the failing test card: the
    generic payment_failed at the authorization step. The agent treats it as
    a card decline and sends a link that hides card."""
    create_order(client)
    generic = payment("pay_fail", "order_A", "failed", error_code="BAD_REQUEST_ERROR",
                      error_reason="payment_failed", error_source="gateway", error_step="payment_authorization")
    view = report_failure(client, generic).json()
    assert view["failure_reason"] == "card_declined"
    assert view["recommended_action"] == "suggest_alternate_method"
    assert view["current_request"]["excluded_method"] == "card"


def test_token_never_appears_whole_in_the_audit_trail(client):
    token = awaiting(client)
    trail = session(client).json()["audit_trail"]
    assert all(token not in e["detail"] for e in trail)


def test_customer_pays_and_the_recovery_is_verified(client, isolated_state_db):
    token = awaiting(client)
    customer = TestClient(isolated_state_db.app)          # no session: the token is the customer's access
    view = customer.get(f"/api/recover/{token}").json()
    assert view["status"] == "open" and view["amount"] == 1000 and view["merchant"]

    r = pay_request(customer, token, "order_R1")
    assert r.status_code == 200
    assert r.json()["status"] == "paid" and r.json()["amount_recovered"] == 1000

    op = session(client).json()
    assert op["stage"] == "recovered"
    assert op["result"]["recovery_order_id"] == "order_R1"
    assert op["result"]["outcome_is_simulated"] is False


def test_recovery_order_is_created_once_for_the_original_amount(client):
    token = awaiting(client)
    with patch("main.create_real_order", return_value={"id": "order_R1", "amount": 1000, "currency": "INR"}) as create:
        first = client.post(f"/api/recover/{token}/order")
        second = client.post(f"/api/recover/{token}/order")
    assert first.status_code == second.status_code == 200
    assert first.json()["order"]["id"] == second.json()["order"]["id"] == "order_R1"
    assert create.call_count == 1
    assert create.call_args.kwargs["amount"] == 1000


# ---- B2: the recovery order is bound to the request ---------------------------

def test_payment_on_another_order_is_rejected(client):
    token = awaiting(client)
    assert customer_order(client, token, "order_R1").status_code == 200
    r = customer_report(client, token, payment("pay_other", "order_X", "captured"))
    assert r.status_code == 400
    assert "not this recovery request's order" in r.json()["detail"]


def test_original_order_cannot_be_its_own_recovery(client):
    token = awaiting(client)
    assert customer_order(client, token, "order_R1").status_code == 200
    assert customer_report(client, token, payment("pay_orig2", "order_A", "captured")).status_code == 400


def test_report_needs_an_order_first(client):
    token = awaiting(client)
    assert customer_report(client, token, payment("pay_ok", "order_R1", "captured")).status_code == 409


@pytest.mark.parametrize("bad", [{"amount": 50000}, {"currency": "USD"}])
def test_amount_and_currency_must_match(client, bad):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    r = customer_report(client, token, {**payment("pay_ok", "order_R1", "captured"), **bad})
    assert r.status_code == 400


def test_unknown_and_malformed_tokens(client):
    assert client.get("/api/recover/rr_" + "x" * 32).status_code == 404
    assert client.get("/api/recover/not-a-token").status_code == 422
    assert client.post("/api/recover/rr_" + "x" * 32 + "/report", params={"payment_id": "pay_a"}).status_code == 404


# ---- B3: stages only move forward ----------------------------------------------

def test_failure_cannot_be_reported_twice(client):
    awaiting(client)
    assert report_failure(client).status_code == 409


def test_finished_session_cannot_be_reset_or_recovered_again(client):
    token = awaiting(client)
    assert pay_request(client, token, "order_R1").status_code == 200
    assert report_failure(client).status_code == 409                       # the old reset trick
    assert customer_report(client, token, payment("pay_R1", "order_R1", "captured")).status_code == 409
    assert customer_order(client, token, "order_R2").status_code == 409


def test_unknown_session_is_404(client):
    assert report_failure(client, order_id="order_nope").status_code == 404
    assert session(client, "order_nope").status_code == 404


# ---- payments still in flight ----------------------------------------------------

def test_non_final_payment_does_not_record_an_outcome(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    assert customer_report(client, token, payment("pay_slow", "order_R1", "authorized")).status_code == 409
    assert session(client).json()["stage"] == "awaiting_customer"
    assert customer_report(client, token, payment("pay_slow", "order_R1", "captured")).status_code == 200


# ---- P1-3: a payment can't be counted twice ---------------------------------------

def test_captured_payment_cannot_recover_a_second_session(client):
    token_a = awaiting(client)
    ok_a = payment("pay_okA", "order_RA", "captured")
    customer_order(client, token_a, "order_RA")
    assert customer_report(client, token_a, ok_a).status_code == 200

    token_b = awaiting(client, "order_B", failed("pay_failB", "order_B"))
    customer_order(client, token_b, "order_RB")
    assert customer_report(client, token_b, ok_a).status_code == 400


def test_failure_payment_from_another_session_is_rejected(client):
    awaiting(client)
    create_order(client, "order_B")
    assert report_failure(client, failed(order_id="order_A"), order_id="order_B").status_code == 400


# ---- P7: a failed attempt re-plans to the next action ------------------------------

def test_failed_payment_replans_to_an_alternate_method(client):
    first = awaiting(client)
    r = pay_request(client, first, "order_R1", status="failed")
    assert r.status_code == 200
    assert r.json()["status"] == "failed"

    view = session(client).json()
    assert view["stage"] == "awaiting_customer"
    assert view["recovery_attempts"] == 2
    assert view["recommended_action"] == "suggest_alternate_method"
    second = token_of(view)
    assert second != first
    assert view["current_request"]["excluded_method"] == "card"
    assert len(view["outbox"]) == 2
    customer = client.get(f"/api/recover/{second}").json()
    assert customer["checkout_config"] == {"display": {"hide": [{"method": "card"}],
                                                       "preferences": {"show_default_blocks": True}}}


def test_old_request_cannot_be_paid_after_a_replan(client):
    first = awaiting(client)
    pay_request(client, first, "order_R1", status="failed")
    assert customer_order(client, first, "order_R9").status_code == 409
    assert client.get(f"/api/recover/{first}").json()["status"] == "failed"


def test_safety_gate_stops_after_max_attempts(client):
    from recovery_agent import MAX_ATTEMPTS
    token = awaiting(client)
    for n in range(1, MAX_ATTEMPTS + 1):
        assert pay_request(client, token, f"order_R{n}", status="failed").status_code == 200
        view = session(client).json()
        if view["current_request"]:
            token = token_of(view)

    assert view["stage"] == "held"
    assert view["recovery_attempts"] == MAX_ATTEMPTS
    assert "MAX_ATTEMPTS" in view["audit_trail"][-1]["detail"]
    assert [m["action"] for m in view["outbox"]] == ["retry_same_method", "suggest_alternate_method", "send_reminder_link"]
    with patch("main.create_real_order") as create:
        assert client.post(f"/api/recover/{token}/order").status_code == 409
    create.assert_not_called()


def test_reminder_that_fails_escalates_to_support(client):
    token = awaiting(client, pay=failed(error_reason="insufficient_fund"))
    assert session(client).json()["recommended_action"] == "send_reminder_link"
    pay_request(client, token, "order_R1", status="failed")
    view = session(client).json()
    assert view["stage"] == "escalated"
    assert view["support_case"]["id"].startswith("case_")
    assert view["current_request"] is None
    assert client.get(f"/api/recover/{token}").json()["status"] == "escalated"


def test_unknown_reason_opens_a_support_case_without_asking_for_money(client):
    create_order(client)
    view = report_failure(client, failed(error_reason="payment_failed")).json()
    assert view["recommended_action"] == "escalate_to_support"
    assert view["stage"] == "escalated"
    assert view["outbox"] == [] and view["current_request"] is None
    assert view["support_case"]["failure_reason"] == "unknown"


# ---- P7: delays and expiry ------------------------------------------------------------

def test_retry_with_delay_is_not_payable_until_the_delay_passes(client):
    token = awaiting(client, pay=failed(error_reason="bank_technical_error"))
    view = client.get(f"/api/recover/{token}").json()
    assert view["action"] == "retry_with_delay"
    assert view["status"] == "scheduled" and 25 <= view["seconds_until_available"] <= 30
    with patch("main.create_real_order") as create:
        r = client.post(f"/api/recover/{token}/order")
    assert r.status_code == 409 and "Not yet" in r.json()["detail"]
    create.assert_not_called()

    later = time.time() + 31
    with patch("main.time.time", return_value=later):
        assert client.get(f"/api/recover/{token}").json()["status"] == "open"
        assert customer_order(client, token, "order_R1").status_code == 200


def test_unpaid_request_expires_and_replans(client, isolated_state_db, monkeypatch):
    monkeypatch.setattr(isolated_state_db, "RECOVERY_REQUEST_TTL_SECONDS", -1)
    first = awaiting(client)
    view = session(client).json()                     # the operator's poll notices the expiry
    assert view["recovery_attempts"] == 2
    assert view["recommended_action"] == "suggest_alternate_method"
    assert client.get(f"/api/recover/{first}").json()["status"] == "expired"
    assert any("didn't pay before the request expired" in e["detail"] for e in view["audit_trail"])


# ---- P2-1: only a payment that actually failed starts a recovery -------------------

@pytest.mark.parametrize("status, code", [
    ("captured", 400), ("refunded", 400), ("created", 409), ("authorized", 409),
])
def test_report_failure_rejects_payments_that_did_not_fail(client, status, code):
    create_order(client)
    r = report_failure(client, payment("pay_s", "order_A", status))
    assert r.status_code == code
    assert status in r.json()["detail"]
    assert session(client).json()["stage"] == "order_created"


# ---- P1-5: Checkout signature on a successful recovery ----------------------------

@pytest.mark.parametrize("signature", [
    None, "0" * 64, "not-hex",
    sign("order_A", "pay_ok"),          # signed for the original order, not the recovery order
    sign("order_R1", "pay_other"),      # signed for a different payment
])
def test_captured_recovery_needs_a_valid_signature(client, signature):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    r = customer_report(client, token, payment("pay_ok", "order_R1", "captured"), signature=signature)
    assert r.status_code == 400
    assert "signature" in r.json()["detail"]
    assert session(client).json()["stage"] == "awaiting_customer"


def test_failed_attempt_needs_no_signature(client):
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    assert customer_report(client, token, payment("pay_x", "order_R1", "failed"), signature=None).status_code == 200


# ---- races ---------------------------------------------------------------------------

def test_two_simultaneous_reports_record_only_one(client, isolated_state_db):
    main = isolated_state_db
    token = awaiting(client)
    customer_order(client, token, "order_R1")
    barrier = threading.Barrier(2)

    def slow_fetch(_payment_id):
        barrier.wait(timeout=5)   # both requests are past the first checks
        return payment("pay_ok", "order_R1", "captured")

    outcomes = []

    def submit():
        try:
            main.recovery_report(token=token, payment_id="pay_ok", razorpay_signature=sign("order_R1", "pay_ok"))
            outcomes.append(200)
        except HTTPException as e:
            outcomes.append(e.status_code)

    with patch("main.fetch_real_payment", side_effect=slow_fetch):
        threads = [threading.Thread(target=submit) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert sorted(outcomes) == [200, 409]
