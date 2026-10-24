"""
Real Razorpay test-mode integration.

IMPORTANT — what is real vs simulated here:
  - create_real_order(): a genuine call to Razorpay's Orders API
    (https://api.razorpay.com/v1/orders). Returns a real order id
    (order_...) and echoes back the real amount/currency Razorpay
    stored. This requires network access to api.razorpay.com and
    valid test-mode keys in the environment — it will NOT work inside
    a sandboxed/offline environment. Run it from your own machine.
  - fetch_real_payment(): fetches a real payment object for a
    payment_id, e.g. after a live Checkout test-card flow, and
    extracts Razorpay's OWN error_code / error_description for that
    failure. This is real gateway data, not invented.
  - The RAZORPAY_ERROR_TAXONOMY below is Razorpay's own documented
    error catalogue (error codes + reasons from their public test
    card docs) — used to tag batch-generated records with realistic,
    correctly-labelled failure reasons when we are not driving a
    browser checkout for every one of 50+ records. This is real
    Razorpay taxonomy, just not a live API round-trip per record.
  - Nothing about whether a RETRY succeeds is ever real — Razorpay
    test mode cannot simulate "customer tries again and it works"
    headlessly. That stays in recovery_agent.py, clearly flagged
    is_simulated=True.
"""
import os
from typing import Optional
import razorpay
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv

from models import FailureReason, RazorpaySource

load_dotenv()  # reads backend/.env if present

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

DEFAULT_TIMEOUT = 8  # seconds — fail fast rather than hanging a batch run


class _TimeoutHTTPAdapter(HTTPAdapter):
    """requests doesn't honor a bare session.timeout attribute — it must be
    applied per adapter/request. This mounts a default timeout on every
    call the razorpay SDK's session makes, so a network stall fails fast
    instead of hanging an entire batch run."""
    def __init__(self, *args, timeout=DEFAULT_TIMEOUT, **kwargs):
        self._timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return super().send(request, **kwargs)


def get_client() -> razorpay.Client:
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise RuntimeError(
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set. Get your TEST MODE "
            "keys from Dashboard -> Settings -> API Keys and export them as "
            "env vars before calling live Razorpay functions."
        )
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    adapter = _TimeoutHTTPAdapter(timeout=DEFAULT_TIMEOUT)
    client.session.mount("https://", adapter)
    client.session.mount("http://", adapter)
    return client


def create_real_order(amount: int, currency: str = "INR", receipt: Optional[str] = None) -> dict:
    """
    Genuine call to POST /v1/orders. Returns Razorpay's real response
    dict, including the real 'id' (order_...), 'amount', 'currency',
    'status'. Requires network access + valid test keys.
    """
    client = get_client()
    order = client.order.create({
        "amount": amount,
        "currency": currency,
        "receipt": receipt or "recovery_agent_batch",
        "payment_capture": 1,
    })
    return order


def fetch_real_payment(payment_id: str) -> dict:
    """
    Genuine call to GET /v1/payments/:id. Returns Razorpay's real
    payment object, including error_code / error_description /
    error_reason for failed payments — actual gateway data.
    """
    client = get_client()
    return client.payment.fetch(payment_id)


def classify_real_payment_error(payment: dict) -> tuple:
    """
    Maps a REAL Razorpay payment object's error_reason (from
    fetch_real_payment) to our internal FailureReason enum. This is
    the live-demo counterpart to the offline RAZORPAY_ERROR_TAXONOMY
    tagging used for batch records — here the error_reason string
    comes directly from Razorpay's own response, not assigned by us.

    Returns (FailureReason, raw_error_code_string).
    """
    from models import FailureReason  # local import to avoid circularity at module load

    error_reason = (payment.get("error_reason") or "").lower()
    error_code = payment.get("error_code", "")
    error_description = payment.get("error_description", "")
    raw = f"{error_code} / {error_reason or 'unknown'}"

    reason_map = {
        "payment_declined": FailureReason.CARD_DECLINED,
        "payment_failed": FailureReason.CARD_DECLINED,
        "payment_timed_out": FailureReason.BANK_TIMEOUT,
        "payment_cancelled": FailureReason.NETWORK_ERROR,
        "payment_error": FailureReason.NETWORK_ERROR,
        "server_error": FailureReason.ISSUER_UNAVAILABLE,
    }
    failure_reason = reason_map.get(error_reason, FailureReason.CARD_DECLINED)
    return failure_reason, raw


# Razorpay's own documented error taxonomy (from their public test-card /
# error-code docs) — used to assign realistic, correctly-labelled failure
# reasons across a generated batch. Source: razorpay.com/docs/payments/
# payments/test-card-details and Cards Error Codes reference.
RAZORPAY_ERROR_TAXONOMY: dict[FailureReason, dict] = {
    FailureReason.CARD_DECLINED: {
        "raw_error_code": "BAD_REQUEST_ERROR / card_declined",
        "description": "The card was declined by the issuing bank.",
    },
    FailureReason.INSUFFICIENT_FUNDS: {
        "raw_error_code": "GATEWAY_ERROR / insufficient_funds",
        "description": "Your payment could not be completed due to insufficient funds.",
    },
    FailureReason.BANK_TIMEOUT: {
        "raw_error_code": "GATEWAY_ERROR / payment_timed_out",
        "description": "Your payment could not be completed due to a temporary issue. Try again later.",
    },
    FailureReason.NETWORK_ERROR: {
        "raw_error_code": "SERVER_ERROR / gateway_error",
        "description": "Payment failed due to a temporary network/gateway issue.",
    },
    FailureReason.EXPIRED_CARD: {
        "raw_error_code": "BAD_REQUEST_ERROR / card_expired",
        "description": "The card has expired.",
    },
    FailureReason.INVALID_CVV: {
        "raw_error_code": "BAD_REQUEST_ERROR / invalid_cvv",
        "description": "The CVV entered is invalid.",
    },
    FailureReason.ISSUER_UNAVAILABLE: {
        "raw_error_code": "GATEWAY_ERROR / issuer_unavailable",
        "description": "The card issuing bank's servers are currently down.",
    },
    FailureReason.LIMIT_EXCEEDED: {
        "raw_error_code": "BAD_REQUEST_ERROR / limit_exceeded",
        "description": "The transaction amount exceeds the card's limit.",
    },
    FailureReason.FRAUD_SUSPECTED: {
        "raw_error_code": "GATEWAY_ERROR / fraudulent_transaction_risk",
        "description": "The payment was flagged as a suspected fraudulent transaction.",
    },
}

# Razorpay's documented test-mode UPI IDs / card behavior for a LIVE demo
# subset — real values from their public test-integration docs.
LIVE_DEMO_TEST_INSTRUMENTS = {
    "upi_failure": "failure@razorpay",
    "upi_success": "success@razorpay",
    "card_declined_visa": "4100 2800 0009 0000",   # -> payment_timed_out per Razorpay docs
    "card_success_visa": "4111 1111 1111 1111",
}
