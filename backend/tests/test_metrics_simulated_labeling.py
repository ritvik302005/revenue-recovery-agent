"""
The whole premise of this project is that batch results are simulated
and must never be presented as real recovered money. These tests pin
that contract at the API boundary, not just in code comments.
"""
from unittest.mock import patch

from conftest import sign


def test_metrics_labels_recovery_as_simulated_not_real(client):
    r = client.post("/api/batch/run", params={"n": 20, "try_live_orders": False})
    assert r.status_code == 200

    metrics = client.get("/api/batch/metrics").json()

    summary = metrics["simulated_recovery_summary"]
    assert "total_amount_recovered_inr" in summary
    assert "simulated" in summary["note"].lower()
    assert "razorpay test mode cannot" in summary["note"].lower()


def test_metrics_has_no_stray_top_level_recovery_claim(client):
    """There must be no top-level field claiming money was recovered
    outside the clearly-labeled simulated_recovery_summary block."""
    client.post("/api/batch/run", params={"n": 15, "try_live_orders": False})
    metrics = client.get("/api/batch/metrics").json()

    top_level_keys = set(metrics.keys())
    assert top_level_keys == {
        "razorpay_data_provenance",
        "simulated_recovery_summary",
        "breakdown_by_failure_reason",
    }
    # No stray "amount_recovered", "total_recovered" etc. sitting
    # outside the clearly-labeled simulated block.
    for key in top_level_keys - {"simulated_recovery_summary"}:
        assert "recover" not in key.lower()


def test_provenance_and_recovery_summary_are_kept_separate(client):
    """razorpay_data_provenance describes where ORDER data came from
    (real vs tagged) — it must never itself claim a recovery outcome,
    which is a completely separate (always-simulated) concept."""
    client.post("/api/batch/run", params={"n": 15, "try_live_orders": False})
    metrics = client.get("/api/batch/metrics").json()

    provenance = metrics["razorpay_data_provenance"]
    assert set(provenance.keys()) == {"note", "razorpay_test_orders", "local_orders"}
    assert "synthetic" in provenance["note"].lower()
    assert "do not describe recovery outcomes" in provenance["note"].lower()


def test_metrics_recovery_numbers_match_underlying_results(client):
    """The recovery rate/counts in metrics must match what the actual
    per-payment results say — not a number computed independently that
    could drift from the underlying (simulated) data."""
    run = client.post("/api/batch/run", params={"n": 30, "try_live_orders": False}).json()
    results = run["results"]

    actual_recovered = sum(1 for r in results if r["outcome"] == "recovered")
    actual_total_recovered_paise = sum(r["amount_recovered"] for r in results)

    metrics = client.get("/api/batch/metrics").json()["simulated_recovery_summary"]
    assert metrics["recovered"] == actual_recovered
    assert round(actual_total_recovered_paise / 100, 2) == metrics["total_amount_recovered_inr"]

    # Every single result must itself be flagged as simulated — the
    # per-record source of truth metrics are aggregated from.
    assert all(r["outcome_is_simulated"] is True for r in results)


def test_batch_saved_by_an_older_version_is_ignored_not_a_crash(client, isolated_state_db):
    """state.db files from before the provenance rename hold
    'real_order_tagged_failure'. They must not 500 every batch endpoint."""
    client.post("/api/batch/run", params={"n": 3, "try_live_orders": False})
    stored = isolated_state_db.storage.get_value("batch:last_results")
    for item in stored["items"]:
        item["razorpay_source"] = "real_order_tagged_failure"
    isolated_state_db.storage.set_value("batch:last_results", stored)

    body = client.get("/api/batch/results").json()
    assert (body["count"], body["results"]) == (0, [])
    assert client.get("/api/batch/metrics").status_code == 404
    assert client.get("/api/showcase/case").json() == {"kind": "none"}


def test_metrics_endpoint_404s_before_any_batch_has_run(client):
    """No batch run yet must be a clear 404, not an empty/zeroed
    'simulated_recovery_summary' that could be misread as '0 recovered
    for real'."""
    r = client.get("/api/batch/metrics")
    assert r.status_code == 404


def test_live_demo_result_is_never_labeled_simulated(client, isolated_state_db):
    """The flip side of the same contract: a genuinely real live-demo
    recovery must be marked outcome_is_simulated=False, so the two
    kinds of evidence are never confused in either direction."""
    main = isolated_state_db

    main._set_demo_record("order_live", {
        "amount": 1000,
        "stage": "recovery_order_created",
        "current_recovery_order_id": "order_R",
        "original_payment_id": "pay_original",
        "failure_reason": "card_declined",
        "raw_error_code": "x",
        "recommended_action": "suggest_alternate_method",
        "safety_check_passed": True,
        "audit_trail": [],
    })

    matching_payment = {"order_id": "order_R", "amount": 1000, "currency": "INR", "status": "captured"}
    with patch("main.fetch_real_payment", return_value=matching_payment):
        r = client.post(
            "/api/live-demo/report-recovery",
            params={"order_id": "order_live", "recovery_order_id": "order_R", "recovery_payment_id": "pay_Y",
                    "razorpay_signature": sign("order_R", "pay_Y")},
        )
    assert r.status_code == 200
    assert r.json()["outcome_is_simulated"] is False
