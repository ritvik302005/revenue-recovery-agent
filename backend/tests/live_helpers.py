"""
Helpers for live-demo tests: Razorpay is mocked (create_real_order,
fetch_real_payment in main); nothing here hits the network.
"""
from unittest.mock import patch

from conftest import sign


def order(order_id, amount=1000):
    return {"id": order_id, "amount": amount, "currency": "INR", "status": "created"}


def payment(payment_id, order_id, status, amount=1000, method="card", **extra):
    return {"id": payment_id, "order_id": order_id, "amount": amount, "currency": "INR",
            "status": status, "method": method, **extra}


def failed(payment_id="pay_fail", order_id="order_A", error_reason="payment_timed_out", method="card"):
    """payment_timed_out is what Razorpay's failing test card returns -> bank_timeout -> retry_same_method."""
    return payment(payment_id, order_id, "failed", method=method,
                   error_code="BAD_REQUEST_ERROR", error_reason=error_reason)


def create_order(client, order_id="order_A"):
    with patch("main.create_real_order", return_value=order(order_id)):
        r = client.post("/api/live-demo/create-order", json={"amount": 1000})
    assert r.status_code == 200
    return r


def report_failure(client, pay=None, order_id="order_A"):
    pay = pay or failed(order_id=order_id)
    with patch("main.fetch_real_payment", return_value=pay):
        return client.post("/api/live-demo/report-failure", params={"order_id": order_id, "payment_id": pay["id"]})


def session(client, order_id="order_A"):
    return client.get("/api/live-demo/session", params={"order_id": order_id})


def token_of(view):
    return view["current_request"]["link"].rsplit("/", 1)[1]


def awaiting(client, order_id="order_A", pay=None):
    """A session whose failure was recorded and executed; returns the request token."""
    create_order(client, order_id)
    r = report_failure(client, pay or failed(order_id=order_id), order_id)
    assert r.status_code == 200, r.text
    return token_of(r.json())


def customer_order(client, token, rzp_order_id):
    with patch("main.create_real_order", return_value=order(rzp_order_id)):
        return client.post(f"/api/recover/{token}/order")


def customer_report(client, token, pay, signature="auto"):
    """Report the customer's Checkout result. A captured payment gets the
    signature Checkout would return unless the test passes its own (or None)."""
    params = {"payment_id": pay["id"]}
    if signature == "auto":
        signature = sign(pay["order_id"], pay["id"]) if pay["status"] == "captured" else None
    if signature is not None:
        params["razorpay_signature"] = signature
    with patch("main.fetch_real_payment", return_value=pay):
        return client.post(f"/api/recover/{token}/report", params=params)


def pay_request(client, token, rzp_order_id, status="captured", payment_id=None):
    """The customer opens the request, gets an order and pays it."""
    assert customer_order(client, token, rzp_order_id).status_code == 200
    return customer_report(client, token, payment(payment_id or f"pay_{rzp_order_id[6:]}", rzp_order_id, status))
