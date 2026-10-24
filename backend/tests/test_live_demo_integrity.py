"""
Live-demo payment integrity: the recovery order is created and bound by
the server, session stages only move forward, and replays or races can't
record a recovery twice. Razorpay is mocked; nothing here hits the network.
"""
import threading
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from conftest import sign


def _order(order_id, amount=1000):
    return {"id": order_id, "amount": amount, "currency": "INR", "status": "created"}


def _payment(payment_id, order_id, status, amount=1000, **extra):
    return {"id": payment_id, "order_id": order_id, "amount": amount, "currency": "INR",
            "status": status, **extra}


FAILED_ON_A = _payment("pay_fail", "order_A", "failed",
                       error_code="BAD_REQUEST_ERROR", error_reason="payment_declined")


def _create_order(client, order_id="order_A"):
    with patch("main.create_real_order", return_value=_order(order_id)):
        r = client.post("/api/live-demo/create-order", json={"amount": 1000})
    assert r.status_code == 200
    return r


def _report_failure(client, payment=FAILED_ON_A, order_id="order_A"):
    with patch("main.fetch_real_payment", return_value=payment):
        return client.post("/api/live-demo/report-failure",
                           params={"order_id": order_id, "payment_id": payment["id"]})


def _create_recovery(client, recovery_order_id="order_R1", order_id="order_A"):
    with patch("main.create_real_order", return_value=_order(recovery_order_id)):
        return client.post("/api/live-demo/create-recovery-order", params={"order_id": order_id})


def _report_recovery(client, payment, recovery_order_id, order_id="order_A", signature="auto"):
    """Report a recovery attempt. A captured payment gets the signature
    Checkout would return for (recovery_order_id, payment id) unless the
    test passes its own (or None)."""
    params = {"order_id": order_id, "recovery_order_id": recovery_order_id,
              "recovery_payment_id": payment["id"]}
    if signature == "auto":
        signature = sign(recovery_order_id, payment["id"]) if payment["status"] == "captured" else None
    if signature is not None:
        params["razorpay_signature"] = signature
    with patch("main.fetch_real_payment", return_value=payment):
        return client.post("/api/live-demo/report-recovery", params=params)


@pytest.fixture()
def failed_session(client):
    """A session with a recorded failure, ready for a recovery order."""
    _create_order(client)
    assert _report_failure(client).status_code == 200
    return client


@pytest.fixture()
def recovery_ready(failed_session):
    """A session with a server-created recovery order order_R1."""
    r = _create_recovery(failed_session)
    assert r.status_code == 200
    return failed_session


# ---- happy path ------------------------------------------------------------

def test_full_flow_records_a_real_recovery(recovery_ready, isolated_state_db):
    r = _report_recovery(recovery_ready, _payment("pay_ok", "order_R1", "captured"), "order_R1")
    assert r.status_code == 200
    body = r.json()
    assert body["recovery_outcome"] == "recovered"
    assert body["recovery_order_id"] == "order_R1"
    assert body["outcome_is_simulated"] is False
    assert body["stage"] == "recovered"
    assert isolated_state_db._get_demo_record("order_A")["stage"] == "recovered"


def test_create_recovery_order_uses_the_original_amount(failed_session):
    with patch("main.create_real_order", return_value=_order("order_R1")) as create:
        r = failed_session.post("/api/live-demo/create-recovery-order", params={"order_id": "order_A"})
    assert r.status_code == 200
    assert create.call_args.kwargs["amount"] == 1000


# ---- B2: the recovery order is bound to the session ------------------------

def test_recovery_on_an_order_the_server_did_not_create_is_rejected(recovery_ready):
    # A genuinely captured payment, but on some other order in the account.
    r = _report_recovery(recovery_ready, _payment("pay_other", "order_X", "captured"), "order_X")
    assert r.status_code == 400
    assert "not the recovery order created" in r.json()["detail"]


def test_original_order_cannot_be_its_own_recovery_order(recovery_ready):
    r = _report_recovery(recovery_ready, _payment("pay_orig2", "order_A", "captured"), "order_A")
    assert r.status_code == 400


def test_recovery_report_needs_a_recovery_order_first(failed_session):
    r = _report_recovery(failed_session, _payment("pay_ok", "order_R1", "captured"), "order_R1")
    assert r.status_code == 409


# ---- B3: stages only move forward ------------------------------------------

def test_failure_cannot_be_reported_twice(failed_session):
    r = _report_failure(failed_session)
    assert r.status_code == 409


def test_finished_session_cannot_be_reset_or_recovered_again(recovery_ready):
    ok = _payment("pay_ok", "order_R1", "captured")
    assert _report_recovery(recovery_ready, ok, "order_R1").status_code == 200

    assert _report_failure(recovery_ready).status_code == 409          # the old reset trick
    assert _report_recovery(recovery_ready, ok, "order_R1").status_code == 409
    assert _create_recovery(recovery_ready, "order_R2").status_code == 409


def test_second_recovery_order_while_one_is_open_is_rejected(recovery_ready):
    assert _create_recovery(recovery_ready, "order_R2").status_code == 409


def test_unknown_session_is_404_everywhere(client):
    assert _report_failure(client, order_id="order_nope").status_code == 404
    assert _create_recovery(client, order_id="order_nope").status_code == 404


# ---- payments still in flight ----------------------------------------------

def test_non_final_payment_does_not_record_an_outcome(recovery_ready, isolated_state_db):
    r = _report_recovery(recovery_ready, _payment("pay_slow", "order_R1", "authorized"), "order_R1")
    assert r.status_code == 409
    assert isolated_state_db._get_demo_record("order_A")["stage"] == "recovery_order_created"

    r = _report_recovery(recovery_ready, _payment("pay_slow", "order_R1", "captured"), "order_R1")
    assert r.status_code == 200


# ---- P1-3: a payment can't be counted twice ----------------------------------

def _second_session(client):
    """Session B with its own recorded failure and recovery order order_R_B."""
    _create_order(client, "order_B")
    failed_b = _payment("pay_fail_b", "order_B", "failed", error_reason="payment_declined")
    assert _report_failure(client, failed_b, order_id="order_B").status_code == 200
    assert _create_recovery(client, "order_R_B", order_id="order_B").status_code == 200


def test_captured_payment_cannot_recover_a_second_session(recovery_ready):
    ok_a = _payment("pay_ok", "order_R1", "captured")
    assert _report_recovery(recovery_ready, ok_a, "order_R1").status_code == 200

    _second_session(recovery_ready)
    # Same captured payment, offered to session B (with A's recovery order, or B's).
    assert _report_recovery(recovery_ready, ok_a, "order_R1", order_id="order_B").status_code == 400
    assert _report_recovery(recovery_ready, ok_a, "order_R_B", order_id="order_B").status_code == 400


def test_original_failed_payment_cannot_be_submitted_as_the_recovery(recovery_ready):
    # Even if it were somehow captured later, it belongs to the original order.
    reused = _payment("pay_fail", "order_A", "captured")
    assert _report_recovery(recovery_ready, reused, "order_R1").status_code == 400


def test_failure_payment_from_another_session_is_rejected(recovery_ready):
    _create_order(recovery_ready, "order_B")
    assert _report_failure(recovery_ready, FAILED_ON_A, order_id="order_B").status_code == 400


# ---- P1-4: retry after a failed recovery, within the retry budget -------------

def _fail_attempt(client, recovery_order_id):
    r = _report_recovery(client, _payment(f"pay_x_{recovery_order_id}", recovery_order_id, "failed"),
                         recovery_order_id)
    assert r.status_code == 200
    return r.json()


def test_failed_recovery_can_be_retried_with_a_new_order(recovery_ready, isolated_state_db):
    first = _fail_attempt(recovery_ready, "order_R1")
    assert first["recovery_outcome"] == "still_failed"
    assert first["stage"] == "recovery_failed"
    assert first["recovery_attempts"] == 1

    assert _create_recovery(recovery_ready, "order_R2").status_code == 200
    r = _report_recovery(recovery_ready, _payment("pay_ok2", "order_R2", "captured"), "order_R2")
    assert r.status_code == 200
    assert r.json()["recovery_outcome"] == "recovered"
    assert r.json()["recovery_attempts"] == 2


def test_stale_recovery_order_is_rejected_after_a_new_one(recovery_ready):
    _fail_attempt(recovery_ready, "order_R1")
    assert _create_recovery(recovery_ready, "order_R2").status_code == 200
    r = _report_recovery(recovery_ready, _payment("pay_late", "order_R1", "captured"), "order_R1")
    assert r.status_code == 400


def test_safety_gate_blocks_the_attempt_after_max_attempts(recovery_ready, isolated_state_db):
    from recovery_agent import MAX_ATTEMPTS
    _fail_attempt(recovery_ready, "order_R1")
    for n in range(2, MAX_ATTEMPTS + 1):
        assert _create_recovery(recovery_ready, f"order_R{n}").status_code == 200
        _fail_attempt(recovery_ready, f"order_R{n}")

    with patch("main.create_real_order") as create:
        r = recovery_ready.post("/api/live-demo/create-recovery-order", params={"order_id": "order_A"})
    assert r.status_code == 409
    assert "Safety gate" in r.json()["detail"]
    create.assert_not_called()          # no real order once the budget is used

    record = isolated_state_db._get_demo_record("order_A")
    assert record["stage"] == "held"
    assert record["recovery_attempts"] == MAX_ATTEMPTS
    assert "MAX_ATTEMPTS" in record["audit_trail"][-1]["detail"]
    assert _create_recovery(recovery_ready, "order_R9").status_code == 409


# ---- P1-5: Checkout signature on a successful recovery -------------------------

@pytest.mark.parametrize("signature", [
    None,                                   # missing
    "0" * 64,                               # wrong
    "not-hex",                              # malformed
    sign("order_A", "pay_ok"),              # signed for the original order, not the recovery order
    sign("order_R1", "pay_other"),          # signed for a different payment
])
def test_captured_recovery_needs_a_valid_signature(recovery_ready, isolated_state_db, signature):
    r = _report_recovery(recovery_ready, _payment("pay_ok", "order_R1", "captured"), "order_R1",
                         signature=signature)
    assert r.status_code == 400
    assert "signature" in r.json()["detail"]
    assert isolated_state_db._get_demo_record("order_A")["stage"] == "recovery_order_created"


def test_failed_recovery_attempt_needs_no_signature(recovery_ready):
    # Razorpay's payment.failed event carries no signature.
    r = _report_recovery(recovery_ready, _payment("pay_x", "order_R1", "failed"), "order_R1", signature=None)
    assert r.status_code == 200
    assert r.json()["recovery_outcome"] == "still_failed"


# ---- races -------------------------------------------------------------------

def test_two_simultaneous_recovery_reports_record_only_one(recovery_ready, isolated_state_db):
    main = isolated_state_db
    barrier = threading.Barrier(2)

    def slow_fetch(_payment_id):
        barrier.wait(timeout=5)   # both requests have passed the first stage check
        return _payment("pay_ok", "order_R1", "captured")

    outcomes = []

    def submit():
        try:
            main.report_recovery(order_id="order_A", recovery_payment_id="pay_ok", recovery_order_id="order_R1",
                                 razorpay_signature=sign("order_R1", "pay_ok"))
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
