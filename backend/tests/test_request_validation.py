"""
Request validation on the endpoints that act (P5-10): bad input is a 422
before any Razorpay call and before any order budget is spent, and the
browser can't choose what is sent to Razorpay as the receipt.
"""
from unittest.mock import patch

import pytest

import access


@pytest.mark.parametrize("body", [
    {"amount": 99},              # below ₹1
    {"amount": 100_001},         # above ₹1,000
    {"amount": "ten"},
    {"amount": 1000, "label": ""},
    {"amount": 1000, "label": "x" * 41},
    {"amount": 1000, "label": "drop table;"},
    {"amount": 1000, "label": "../../receipt"},
])
def test_bad_create_order_body_is_rejected_before_razorpay(client, body):
    with patch("main.create_real_order") as order:
        r = client.post("/api/live-demo/create-order", json=body)
    assert r.status_code == 422
    order.assert_not_called()


def test_rejected_request_spends_no_order_budget(isolated_state_db, monkeypatch):
    from conftest import new_session_client
    monkeypatch.setattr(access, "ORDERS_PER_SESSION", 1)
    c = new_session_client(isolated_state_db)
    assert c.post("/api/live-demo/create-order", json={"amount": 5}).status_code == 422
    with patch("main.create_real_order", return_value={"id": "order_V1", "amount": 1000, "currency": "INR"}):
        assert c.post("/api/live-demo/create-order", json={"amount": 1000}).status_code == 200


def test_receipt_is_generated_server_side(client):
    with patch("main.create_real_order", return_value={"id": "order_V2", "amount": 1000, "currency": "INR"}) as order:
        client.post("/api/live-demo/create-order", json={"amount": 1000, "label": "my_label"})
    receipt = order.call_args.kwargs["receipt"]
    assert receipt.startswith("live_demo_") and "my_label" not in receipt


@pytest.mark.parametrize("params", [
    {"n": 0}, {"n": 501}, {"n": "many"},
    {"n": 10, "seed": -1}, {"n": 10, "seed": 2**31},
])
def test_bad_batch_parameters_are_rejected(client, params):
    with patch("main.generate_batch") as gen:
        r = client.post("/api/batch/run", params=params)
    assert r.status_code == 422
    gen.assert_not_called()
