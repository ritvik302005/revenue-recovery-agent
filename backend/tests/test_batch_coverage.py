"""
Every documented failure category appears in a batch large enough to hold
them all, so each policy and the fraud gate are always exercised. UNKNOWN is
never generated.
"""
import logging

import pytest

from models import FailureReason, Outcome

DOCUMENTED = set(FailureReason) - {FailureReason.UNKNOWN}


@pytest.mark.parametrize("seed", [0, 1, 42, 999, 123456])
def test_every_category_present_when_the_batch_can_hold_them(seed):
    from simulate_batch import generate_batch
    reasons = {p.failure_reason for p in generate_batch(n=60, seed=seed, try_live_orders=False)}
    assert reasons == DOCUMENTED


def test_smallest_batch_that_fits_has_each_category_once():
    from simulate_batch import generate_batch
    batch = generate_batch(n=len(DOCUMENTED), seed=5, try_live_orders=False)
    assert sorted(p.failure_reason.value for p in batch) == sorted(r.value for r in DOCUMENTED)


def test_small_batches_still_work_and_never_use_unknown():
    from simulate_batch import generate_batch
    for seed in range(20):
        batch = generate_batch(n=5, seed=seed, try_live_orders=False)
        assert len(batch) == 5
        assert all(p.failure_reason != FailureReason.UNKNOWN for p in batch)


def test_default_batch_shows_the_fraud_hold(client):
    """Audit bug B8: the default seed-42 batch of 60 used to contain no fraud case."""
    client.post("/api/batch/run", params={"n": 60, "try_live_orders": False})
    summary = client.get("/api/batch/metrics").json()["simulated_recovery_summary"]
    assert summary["held_no_action_fraud"] >= 1


def test_default_batch_reaches_every_outcome(client):
    run = client.post("/api/batch/run", params={"n": 60, "try_live_orders": False}).json()
    outcomes = {r["outcome"] for r in run["results"]}
    assert outcomes == {o.value for o in Outcome}
