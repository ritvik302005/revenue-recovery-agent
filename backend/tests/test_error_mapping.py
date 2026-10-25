"""
Razorpay's documented error_reason values map to the right category, one
table serves both the live demo and the batch, and anything undocumented
is escalated instead of being guessed as "card declined".
"""
from unittest.mock import patch

import pytest

from models import FailureReason, RecoveryAction


# The error reasons Razorpay's test cards produce
# (https://razorpay.com/docs/payments/payments/test-card-details/).
@pytest.mark.parametrize("error_reason, category", [
    ("payment_timed_out", FailureReason.BANK_TIMEOUT),
    ("insufficient_fund", FailureReason.INSUFFICIENT_FUNDS),      # test-card page spelling
    ("insufficient_funds", FailureReason.INSUFFICIENT_FUNDS),     # error-list spelling
    ("payment_cancelled", FailureReason.PAYMENT_CANCELLED),
    ("card_declined", FailureReason.CARD_DECLINED),
    ("card_disabled_for_online_payments", FailureReason.CARD_DECLINED),
    ("card_number_invalid", FailureReason.INVALID_CARD_DETAILS),
    ("gateway_technical_error", FailureReason.NETWORK_ERROR),
    ("authentication_failed", FailureReason.AUTHENTICATION_FAILED),
    # and a few from the error list
    ("card_expired", FailureReason.EXPIRED_CARD),
    ("incorrect_cvv", FailureReason.INVALID_CVV),
    ("issuer_technical_error", FailureReason.ISSUER_UNAVAILABLE),
    ("transaction_daily_limit_exceeded", FailureReason.LIMIT_EXCEEDED),
    ("payment_risk_check_failed", FailureReason.FRAUD_SUSPECTED),
])
def test_documented_reasons_map_to_their_category(error_reason, category):
    from razorpay_client import classify_real_payment_error
    got, raw = classify_real_payment_error({"error_reason": error_reason, "error_code": "BAD_REQUEST_ERROR"})
    assert got == category
    assert raw == f"BAD_REQUEST_ERROR / {error_reason}"


@pytest.mark.parametrize("error_reason", [
    "payment_failed",            # documented as "no specific error code" — unspecific
    "something_razorpay_adds_later",
    "",
    None,
])
def test_unspecific_or_undocumented_reasons_are_unknown(error_reason):
    from razorpay_client import classify_real_payment_error
    got, raw = classify_real_payment_error({"error_reason": error_reason, "error_code": "GATEWAY_ERROR"})
    assert got == FailureReason.UNKNOWN


# What Razorpay test mode actually returned for card 4100 2800 0009 0000 (2026-10-25).
OBSERVED_GENERIC = {"error_reason": "payment_failed", "error_code": "BAD_REQUEST_ERROR",
                    "error_source": "gateway", "error_step": "payment_authorization", "method": "card"}


def test_generic_failure_at_card_authorization_is_a_decline():
    from razorpay_client import classify_real_payment_error
    got, raw = classify_real_payment_error(OBSERVED_GENERIC)
    assert got == FailureReason.CARD_DECLINED
    assert raw == "BAD_REQUEST_ERROR / payment_failed @ payment_authorization"


@pytest.mark.parametrize("change", [
    {"error_step": "payment_initiation"},     # failed before authorization
    {"error_step": None},                     # no step: no evidence
    {"method": "upi"},                        # not a card
    {"method": "netbanking"},
])
def test_generic_failure_without_that_evidence_still_escalates(change):
    from razorpay_client import classify_real_payment_error
    assert classify_real_payment_error({**OBSERVED_GENERIC, **change})[0] == FailureReason.UNKNOWN


def test_mapping_is_case_insensitive():
    from razorpay_client import classify_real_payment_error
    assert classify_real_payment_error({"error_reason": "CARD_DECLINED"})[0] == FailureReason.CARD_DECLINED


def test_batch_examples_use_the_same_table():
    """Every category (except UNKNOWN) has a documented example for the
    batch, and that example's reason maps back to the same category."""
    from razorpay_client import DOCUMENTED_ERROR_EXAMPLES, ERROR_REASON_TO_CATEGORY
    assert set(DOCUMENTED_ERROR_EXAMPLES) == set(FailureReason) - {FailureReason.UNKNOWN}
    for category, example in DOCUMENTED_ERROR_EXAMPLES.items():
        error_reason = example["raw_error_code"].split(" / ")[1]
        assert ERROR_REASON_TO_CATEGORY[error_reason] == category


@pytest.mark.parametrize("category", list(FailureReason))
def test_every_category_has_an_agent_action(category):
    from recovery_agent import select_recovery_action
    from main import _agent_state
    state = select_recovery_action(_agent_state(category, 0, "pay_x", []))
    assert state["action"] is not None
    if category == FailureReason.UNKNOWN:
        assert state["action"] == RecoveryAction.ESCALATE_TO_SUPPORT


# ---- P2-5: malformed ids never reach Razorpay ---------------------------------

BAD_PAYMENT_IDS = ["pay_../orders", "pay_abc/def", "pay_abc?x=1", "pay_", "", "order_abc", "pay_" + "a" * 41, "pay_abc def"]
BAD_ORDER_IDS = ["order_../payments", "order_a/b", "order_", "", "pay_abc", "order_" + "a" * 41]


@pytest.mark.parametrize("payment_id", BAD_PAYMENT_IDS)
def test_report_failure_rejects_malformed_payment_ids(client, payment_id):
    with patch("main.fetch_real_payment") as fetch:
        r = client.post("/api/live-demo/report-failure", params={"order_id": "order_A", "payment_id": payment_id})
    assert r.status_code == 422
    fetch.assert_not_called()


@pytest.mark.parametrize("order_id", BAD_ORDER_IDS)
def test_endpoints_reject_malformed_order_ids(client, order_id):
    with patch("main.fetch_real_payment") as fetch, patch("main.create_real_order") as create:
        responses = [
            client.post("/api/live-demo/report-failure", params={"order_id": order_id, "payment_id": "pay_abc"}),
            client.get("/api/live-demo/session", params={"order_id": order_id}),
        ]
    assert [r.status_code for r in responses] == [422] * 2
    fetch.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize("payment_id", BAD_PAYMENT_IDS)
def test_recovery_report_rejects_malformed_payment_ids(client, payment_id):
    with patch("main.fetch_real_payment") as fetch:
        r = client.post("/api/recover/rr_" + "x" * 32 + "/report", params={"payment_id": payment_id})
    assert r.status_code == 422
    fetch.assert_not_called()


# ---- through the live-demo endpoint -----------------------------------------

def _report(client, error_reason):
    with patch("main.create_real_order",
               return_value={"id": "order_A", "amount": 1000, "currency": "INR", "status": "created"}):
        client.post("/api/live-demo/create-order", json={"amount": 1000})
    payment = {"id": "pay_f", "order_id": "order_A", "amount": 1000, "currency": "INR",
               "status": "failed", "error_code": "BAD_REQUEST_ERROR", "error_reason": error_reason}
    with patch("main.fetch_real_payment", return_value=payment):
        return client.post("/api/live-demo/report-failure", params={"order_id": "order_A", "payment_id": "pay_f"})


def test_live_insufficient_funds_gets_a_reminder_link(client):
    body = _report(client, "insufficient_fund").json()
    assert body["failure_reason"] == "insufficient_funds"
    assert body["recommended_action"] == "send_reminder_link"
    assert body["stage"] == "awaiting_customer"
    assert body["outbox"][0]["text"].startswith("Reminder:")


def test_live_risk_check_failure_is_held_by_the_safety_gate(client):
    body = _report(client, "payment_risk_check_failed").json()
    assert body["failure_reason"] == "fraud_suspected"
    assert body["safety_check_passed"] is False
    assert body["stage"] == "held"


def test_live_unknown_reason_escalates_to_support(client):
    body = _report(client, "payment_failed").json()
    assert body["failure_reason"] == "unknown"
    assert body["recommended_action"] == "escalate_to_support"
