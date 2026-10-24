"""
report-recovery must never accept a captured payment as "recovered"
unless it's genuinely the recovery order's own payment, for the
original amount, in the expected currency.
"""
from unittest.mock import patch


def _seed_failure_recorded(main, order_id="order_A", amount=1000):
    """Directly seed a live-demo record in the 'failure_recorded'
    stage, as /report-failure would have left it, so tests can call
    /report-recovery without going through the full Checkout flow."""
    main._set_demo_record(order_id, {
        "amount": amount,
        "stage": "failure_recorded",
        "original_payment_id": "pay_original",
        "failure_reason": "card_declined",
        "raw_error_code": "BAD_REQUEST_ERROR / payment_declined",
        "recommended_action": "suggest_alternate_method",
        "safety_check_passed": True,
        "audit_trail": [],
    })


def test_recovery_rejected_when_payment_belongs_to_different_order(client, isolated_state_db):
    main = isolated_state_db
    _seed_failure_recorded(main, order_id="order_A", amount=1000)

    wrong_order_payment = {"order_id": "order_UNRELATED", "amount": 1000, "currency": "INR", "status": "captured"}
    with patch("main.fetch_real_payment", return_value=wrong_order_payment):
        r = client.post(
            "/api/live-demo/report-recovery",
            params={"order_id": "order_A", "recovery_order_id": "order_R", "recovery_payment_id": "pay_Y"},
        )
    assert r.status_code == 400
    assert "order_UNRELATED" in r.json()["detail"] or "not the claimed recovery_order_id" in r.json()["detail"]


def test_recovery_rejected_when_amount_does_not_match(client, isolated_state_db):
    main = isolated_state_db
    _seed_failure_recorded(main, order_id="order_A", amount=1000)

    wrong_amount_payment = {"order_id": "order_R", "amount": 50000, "currency": "INR", "status": "captured"}
    with patch("main.fetch_real_payment", return_value=wrong_amount_payment):
        r = client.post(
            "/api/live-demo/report-recovery",
            params={"order_id": "order_A", "recovery_order_id": "order_R", "recovery_payment_id": "pay_Y"},
        )
    assert r.status_code == 400
    assert "amount" in r.json()["detail"].lower()


def test_recovery_rejected_on_currency_mismatch(client, isolated_state_db):
    main = isolated_state_db
    _seed_failure_recorded(main, order_id="order_A", amount=1000)

    wrong_currency_payment = {"order_id": "order_R", "amount": 1000, "currency": "USD", "status": "captured"}
    with patch("main.fetch_real_payment", return_value=wrong_currency_payment):
        r = client.post(
            "/api/live-demo/report-recovery",
            params={"order_id": "order_A", "recovery_order_id": "order_R", "recovery_payment_id": "pay_Y"},
        )
    assert r.status_code == 400
    assert "currency" in r.json()["detail"].lower()


def test_recovery_accepted_when_everything_matches(client, isolated_state_db):
    main = isolated_state_db
    _seed_failure_recorded(main, order_id="order_A", amount=1000)

    matching_payment = {"order_id": "order_R", "amount": 1000, "currency": "INR", "status": "captured"}
    with patch("main.fetch_real_payment", return_value=matching_payment):
        r = client.post(
            "/api/live-demo/report-recovery",
            params={"order_id": "order_A", "recovery_order_id": "order_R", "recovery_payment_id": "pay_Y"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["recovery_outcome"] == "recovered"
    assert body["recovery_order_id"] == "order_R"
    assert body["outcome_is_simulated"] is False


def test_recovery_rejected_when_no_failure_was_ever_recorded(client):
    """Calling report-recovery for an order that never went through
    /report-failure must be rejected, not silently accepted."""
    r = client.post(
        "/api/live-demo/report-recovery",
        params={"order_id": "order_never_seen", "recovery_order_id": "order_R", "recovery_payment_id": "pay_Y"},
    )
    assert r.status_code == 404


def test_recovery_requires_recovery_order_id_parameter(client, isolated_state_db):
    """recovery_order_id is required precisely so this validation can
    happen at all — omitting it must fail fast, not fall back to
    trusting the original order_id."""
    main = isolated_state_db
    _seed_failure_recorded(main, order_id="order_A", amount=1000)

    r = client.post(
        "/api/live-demo/report-recovery",
        params={"order_id": "order_A", "recovery_payment_id": "pay_Y"},
    )
    assert r.status_code == 422
