"""
The policy preview runs the agent's real rules on a hypothetical failure,
with no payment and no Razorpay call.
"""
from unittest.mock import patch

import pytest

from razorpay_client import ERROR_REASON_TO_CATEGORY


def test_lists_every_documented_reason(anon_client):
    body = anon_client.get("/api/policy").json()
    assert {r["error_reason"] for r in body["reasons"]} == set(ERROR_REASON_TO_CATEGORY)
    assert body["methods"] == ["card", "upi", "netbanking", "wallet"]


@pytest.mark.parametrize("reason, category, action, kind", [
    ("payment_timed_out", "bank_timeout", "retry_same_method", "payment_request"),
    ("insufficient_funds", "insufficient_funds", "send_reminder_link", "payment_request"),
    ("bank_technical_error", "issuer_unavailable", "retry_with_delay", "payment_request"),
    ("payment_failed", "unknown", "escalate_to_support", "support_case"),
])
def test_preview_matches_the_live_policy(anon_client, reason, category, action, kind):
    with patch("main.create_real_order") as create, patch("main.fetch_real_payment") as fetch:
        body = anon_client.get("/api/policy/preview", params={"error_reason": reason}).json()
    create.assert_not_called()
    fetch.assert_not_called()
    assert (body["category"], body["action"], body["plan"]["kind"]) == (category, action, kind)
    assert body["safety_check_passed"] is True


def test_fraud_is_held_with_no_plan(anon_client):
    body = anon_client.get("/api/policy/preview", params={"error_reason": "payment_risk_check_failed"}).json()
    assert body["safety_check_passed"] is False
    assert body["plan"] is None and body["customer_message"] is None
    assert "BLOCKED" in body["gate"]


def test_alternate_method_hides_the_chosen_method(anon_client):
    reason = next(r for r, c in ERROR_REASON_TO_CATEGORY.items() if c.value == "card_declined")
    body = anon_client.get("/api/policy/preview", params={"error_reason": reason, "method": "upi"}).json()
    assert body["action"] == "suggest_alternate_method"
    assert body["plan"]["excluded_method"] == "upi"
    assert "<link>" in body["customer_message"]


def test_undocumented_reason_is_marked(anon_client):
    body = anon_client.get("/api/policy/preview", params={"error_reason": "made_up_reason"}).json()
    assert body["documented"] is False and body["category"] == "unknown"


@pytest.mark.parametrize("params", [{"error_reason": "Bad-Reason"}, {"error_reason": "x" * 65},
                                    {"error_reason": "payment_failed", "method": "crypto"}, {}])
def test_bad_input_is_rejected(anon_client, params):
    assert anon_client.get("/api/policy/preview", params=params).status_code == 422
