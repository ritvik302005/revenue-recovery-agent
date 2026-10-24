"""
The batch is reproducible: the same seed gives the same synthetic batch and
the same simulated outcomes, and the seed is reported with the results.
"""


def _summary(results):
    return [(r["payment_id"], r["failure_reason"], r["amount"], r["action_taken"],
             r["outcome"], r["attempt_count"], r["amount_recovered"]) for r in results]


def test_same_seed_gives_identical_results(client):
    a = client.post("/api/batch/run", params={"n": 40, "seed": 7, "try_live_orders": False}).json()
    b = client.post("/api/batch/run", params={"n": 40, "seed": 7, "try_live_orders": False}).json()
    assert _summary(a["results"]) == _summary(b["results"])
    assert a["seed"] == b["seed"] == 7


def test_different_seeds_give_different_batches(client):
    a = client.post("/api/batch/run", params={"n": 40, "seed": 1, "try_live_orders": False}).json()
    b = client.post("/api/batch/run", params={"n": 40, "seed": 2, "try_live_orders": False}).json()
    assert _summary(a["results"]) != _summary(b["results"])


def test_default_seed_is_used_and_reported(client):
    run = client.post("/api/batch/run", params={"n": 5, "try_live_orders": False}).json()
    assert run["seed"] == 42
    assert client.get("/api/batch/metrics").json()["simulated_recovery_summary"]["seed"] == 42
    assert client.get("/api/batch/results").json()["seed"] == 42


def test_ids_are_seeded_and_well_formed(client):
    import re
    run = client.post("/api/batch/run", params={"n": 10, "seed": 3, "try_live_orders": False}).json()
    for r in run["results"]:
        assert re.fullmatch(r"pay_[0-9a-f]{14}", r["payment_id"])
        assert re.fullmatch(r"order_[0-9a-f]{14}", r["order_id"])
