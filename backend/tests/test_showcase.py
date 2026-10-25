"""
The landing page's case card shows only a real recorded case: the latest
live-demo result, else a labelled batch record, else an empty state. Every
field must come from the run itself.
"""
from unittest.mock import patch

from live_helpers import awaiting, pay_request, session, token_of


def _live_flow(client, final_status="captured"):
    """A recovered case, or ("failed") one that keeps failing until the
    safety gate holds it."""
    token = awaiting(client)
    if final_status == "captured":
        assert pay_request(client, token, "order_R1", payment_id="pay_ok").status_code == 200
        return
    n = 1
    while token:
        assert pay_request(client, token, f"order_R{n}", status="failed").status_code == 200
        view = session(client).json()
        token = token_of(view) if view["current_request"] else None
        n += 1


def test_empty_state_before_anything_has_run(client):
    assert client.get("/api/showcase/case").json() == {"kind": "none"}


def test_batch_record_is_shown_and_labelled_simulated(client):
    run = client.post("/api/batch/run", params={"n": 20, "try_live_orders": False}).json()
    case = client.get("/api/showcase/case").json()

    assert case["kind"] == "batch_record"
    assert case["outcome_is_simulated"] is True
    assert case["failure_is_synthetic"] is True
    # It is one of the records the batch actually produced, unchanged.
    source = next(r for r in run["results"] if r["payment_id"] == case["payment_id"])
    assert case["outcome"] == source["outcome"]
    assert case["amount"] == source["amount"]
    assert len(case["audit_trail"]) == len(source["audit_trail"])
    assert case["recorded_at"] == source["audit_trail"][-1]["timestamp"]


def test_live_case_takes_priority_and_carries_the_real_ids(client):
    client.post("/api/batch/run", params={"n": 10, "try_live_orders": False})
    _live_flow(client)
    case = client.get("/api/showcase/case").json()

    assert case["kind"] == "live_demo"
    assert case["outcome_is_simulated"] is False
    assert (case["order_id"], case["payment_id"]) == ("order_A", "pay_fail")
    assert (case["recovery_order_id"], case["recovery_payment_id"]) == ("order_R1", "pay_ok")
    assert case["failure_reason"] == "bank_timeout"
    assert case["raw_error_code"] == "BAD_REQUEST_ERROR / payment_timed_out"
    assert case["outcome"] == "recovered"
    assert case["amount_recovered"] == 1000
    assert case["recorded_at"] == case["audit_trail"][-1]["timestamp"]


def test_unrecovered_case_is_recorded_too(client):
    _live_flow(client, final_status="failed")
    case = client.get("/api/showcase/case").json()
    assert case["kind"] == "live_demo"
    assert case["stage"] == "held"
    assert case["outcome"] == "held_no_action"
    assert case["attempts"] == 3
    assert case["amount_recovered"] == 0


def test_fraud_hold_is_recorded(client):
    with patch("main.create_real_order",
               return_value={"id": "order_F", "amount": 1000, "currency": "INR", "status": "created"}):
        client.post("/api/live-demo/create-order", json={"amount": 1000})
    risky = {"id": "pay_risk", "order_id": "order_F", "amount": 1000, "currency": "INR",
             "status": "failed", "error_code": "BAD_REQUEST_ERROR", "error_reason": "payment_risk_check_failed"}
    with patch("main.fetch_real_payment", return_value=risky):
        client.post("/api/live-demo/report-failure", params={"order_id": "order_F", "payment_id": "pay_risk"})
    case = client.get("/api/showcase/case").json()
    assert case["kind"] == "live_demo"
    assert case["stage"] == "held"
    assert case["outcome"] == "held_no_action"
    assert case["safety_check_passed"] is False


def test_live_case_outlives_the_session(client, isolated_state_db):
    _live_flow(client)
    isolated_state_db.storage.delete_value("live_demo:order_A")   # session expired
    assert client.get("/api/showcase/case").json()["kind"] == "live_demo"
