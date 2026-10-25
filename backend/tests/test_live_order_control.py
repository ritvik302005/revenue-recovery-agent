"""
Real Razorpay orders in a batch are opt-in, capped, and stop at the first
failure, so an unreachable Razorpay costs one timeout instead of one per
record (audit bug B4: 60 x 8 s in one request). Razorpay is mocked.
"""
from unittest.mock import patch


def _counting_order(calls):
    def create(amount, receipt):
        calls.append(receipt)
        return {"id": f"order_live{len(calls)}", "amount": amount, "currency": "INR"}
    return create


def test_no_real_orders_by_default(client):
    calls = []
    with patch("simulate_batch.create_real_order", side_effect=_counting_order(calls)):
        run = client.post("/api/batch/run", params={"n": 20}).json()
    assert calls == []
    assert all(r["razorpay_source"] == "local_order" for r in run["results"])


def test_real_orders_are_capped(client):
    from simulate_batch import MAX_LIVE_ORDERS_PER_BATCH
    calls = []
    with patch("simulate_batch.create_real_order", side_effect=_counting_order(calls)):
        run = client.post("/api/batch/run", params={"n": 20, "try_live_orders": True}).json()
    assert len(calls) == MAX_LIVE_ORDERS_PER_BATCH
    sources = [r["razorpay_source"] for r in run["results"]]
    assert sources.count("razorpay_test_order") == MAX_LIVE_ORDERS_PER_BATCH
    metrics = client.get("/api/batch/metrics").json()["razorpay_data_provenance"]
    assert metrics["razorpay_test_orders"] == MAX_LIVE_ORDERS_PER_BATCH
    assert metrics["local_orders"] == 20 - MAX_LIVE_ORDERS_PER_BATCH


def test_first_failure_stops_further_attempts(client):
    calls = []

    def unreachable(amount, receipt):
        calls.append(receipt)
        raise TimeoutError("simulated timeout")

    with patch("simulate_batch.create_real_order", side_effect=unreachable):
        run = client.post("/api/batch/run", params={"n": 60, "try_live_orders": True}).json()
    assert len(calls) == 1
    assert all(r["razorpay_source"] == "local_order" for r in run["results"])


def test_live_orders_do_not_change_the_simulated_outcomes(client):
    """Same seed with and without real orders: only the order ids differ."""
    off = client.post("/api/batch/run", params={"n": 20, "seed": 9}).json()["results"]
    with patch("simulate_batch.create_real_order", side_effect=_counting_order([])):
        on = client.post("/api/batch/run", params={"n": 20, "seed": 9, "try_live_orders": True}).json()["results"]
    assert [(r["payment_id"], r["outcome"]) for r in off] == [(r["payment_id"], r["outcome"]) for r in on]
