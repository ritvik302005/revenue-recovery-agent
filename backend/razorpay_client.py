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
  - ERROR_REASON_TO_CATEGORY below groups Razorpay's documented
    error_reason values (sources linked there) into our categories;
    the live demo maps real payments through it. Batch records are
    labelled with DOCUMENTED_ERROR_EXAMPLES — documented codes, but
    assigned synthetically, not returned by a real payment.
  - Nothing about whether a RETRY succeeds is ever real — Razorpay
    test mode cannot simulate "customer tries again and it works"
    headlessly. That stays in recovery_agent.py, clearly flagged
    is_simulated=True.
"""
import functools
import logging
import os
from datetime import datetime, timezone
from typing import Optional
import razorpay
import razorpay.errors
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv

import storage
from models import FailureReason, RazorpaySource

logger = logging.getLogger(__name__)

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


class RazorpayNotConfigured(RuntimeError):
    """Test keys are missing, so no Razorpay call can be made."""


def get_client() -> razorpay.Client:
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise RazorpayNotConfigured(
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set. Get your TEST MODE "
            "keys from Dashboard -> Settings -> API Keys and export them as "
            "env vars before calling live Razorpay functions."
        )
    if key_mode() == "live":
        # This project only ever moves test-mode money (RULES.md §2).
        raise RazorpayNotConfigured("Live-mode Razorpay keys are configured; this app only runs with test-mode keys.")
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    adapter = _TimeoutHTTPAdapter(timeout=DEFAULT_TIMEOUT)
    client.session.mount("https://", adapter)
    client.session.mount("http://", adapter)
    return client


def key_mode() -> Optional[str]:
    """'test' or 'live' from the key id's prefix (never the key itself); None if unset."""
    if not RAZORPAY_KEY_ID:
        return None
    if RAZORPAY_KEY_ID.startswith("rzp_test_"):
        return "test"
    if RAZORPAY_KEY_ID.startswith("rzp_live_"):
        return "live"
    return "unknown"


# The outcome of the latest real Razorpay calls, for /api/health. Recorded
# by the calls themselves, so health never spends an API call to find out.
HEALTH_KEY = "health:razorpay"


def _record_call(error: Optional[Exception] = None) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if error is None:
        update = {"last_success_at": now}
    else:
        # A BadRequestError means Razorpay answered and refused (bad id,
        # wrong keys); anything else means it couldn't be reached or failed.
        kind = "rejected" if isinstance(error, razorpay.errors.BadRequestError) else "unreachable_or_error"
        update = {"last_failure_at": now, "last_failure_kind": kind}
    try:
        storage.update_atomic(HEALTH_KEY, lambda current: {**(current or {}), **update})
    except Exception:
        logger.warning("Could not record Razorpay call health", exc_info=True)


def _tracked(fn):
    """Record each real call's outcome; missing keys aren't a Razorpay outcome."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except RazorpayNotConfigured:
            raise
        except Exception as e:
            _record_call(e)
            raise
        _record_call()
        return result
    return wrapper


@_tracked
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


@_tracked
def fetch_real_payment(payment_id: str) -> dict:
    """
    Genuine call to GET /v1/payments/:id. Returns Razorpay's real
    payment object, including error_code / error_description /
    error_reason for failed payments — actual gateway data.
    """
    client = get_client()
    return client.payment.fetch(payment_id)


def verify_checkout_signature(order_id: str, payment_id: str, signature: Optional[str]) -> bool:
    """
    Checks the razorpay_signature that Checkout hands the browser on a
    successful payment: HMAC-SHA256 of "order_id|payment_id" with the key
    secret, verified by the SDK (constant-time compare). Proves the success
    callback came from Razorpay for exactly this order and payment.
    Local computation only — no API call.
    """
    if not signature or not RAZORPAY_KEY_SECRET:
        return False
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID or "", RAZORPAY_KEY_SECRET))
    try:
        return bool(client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }))
    except razorpay.errors.SignatureVerificationError:
        return False


# Razorpay's documented payment error reasons (the `error_reason` field on a
# failed payment), grouped into our categories. One table for both paths:
# the live demo maps real payments through it, and the batch draws its
# synthetic error codes from DOCUMENTED_ERROR_EXAMPLES below.
# Sources (checked 2026-10-25):
#   https://razorpay.com/docs/errors/payments/list/
#   https://razorpay.com/docs/payments/payments/test-card-details/
ERROR_REASON_TO_CATEGORY: dict[str, FailureReason] = {
    # Declined by the card network/issuer, or the card can't be used here
    "card_declined": FailureReason.CARD_DECLINED,
    "payment_declined": FailureReason.CARD_DECLINED,
    "debit_declined": FailureReason.CARD_DECLINED,
    "debit_instrument_blocked": FailureReason.CARD_DECLINED,
    "debit_instrument_inactive": FailureReason.CARD_DECLINED,
    "card_disabled_for_online_payments": FailureReason.CARD_DECLINED,
    "card_not_enrolled": FailureReason.CARD_DECLINED,
    "international_transaction_not_allowed": FailureReason.CARD_DECLINED,
    # Balance
    "insufficient_funds": FailureReason.INSUFFICIENT_FUNDS,
    "insufficient_fund": FailureReason.INSUFFICIENT_FUNDS,   # spelling on the test-card page
    "funds_blocked_by_mandate": FailureReason.INSUFFICIENT_FUNDS,
    # Card details
    "card_expired": FailureReason.EXPIRED_CARD,
    "incorrect_cvv": FailureReason.INVALID_CVV,
    "card_number_invalid": FailureReason.INVALID_CARD_DETAILS,
    "incorrect_card_details": FailureReason.INVALID_CARD_DETAILS,
    "incorrect_card_expiry_date": FailureReason.INVALID_CARD_DETAILS,
    "incorrect_cardholder_name": FailureReason.INVALID_CARD_DETAILS,
    "card_type_invalid": FailureReason.INVALID_CARD_DETAILS,
    # Customer authentication (OTP / 3-D Secure / PIN)
    "authentication_failed": FailureReason.AUTHENTICATION_FAILED,
    "incorrect_otp": FailureReason.AUTHENTICATION_FAILED,
    "otp_expired": FailureReason.AUTHENTICATION_FAILED,
    "otp_attempts_exceeded": FailureReason.AUTHENTICATION_FAILED,
    "incorrect_pin": FailureReason.AUTHENTICATION_FAILED,
    "incorrect_atm_pin": FailureReason.AUTHENTICATION_FAILED,
    "pin_attempts_exceeded": FailureReason.AUTHENTICATION_FAILED,
    # Customer cancelled
    "payment_cancelled": FailureReason.PAYMENT_CANCELLED,
    # Ran out of time
    "payment_timed_out": FailureReason.BANK_TIMEOUT,
    "request_timed_out": FailureReason.BANK_TIMEOUT,
    "payment_session_expired": FailureReason.BANK_TIMEOUT,
    "payment_collect_request_expired": FailureReason.BANK_TIMEOUT,
    # Gateway / network / Razorpay side
    "gateway_technical_error": FailureReason.NETWORK_ERROR,
    "invalid_response_from_gateway": FailureReason.NETWORK_ERROR,
    "server_error": FailureReason.NETWORK_ERROR,
    "payment_declined_due_to_high_traffic": FailureReason.NETWORK_ERROR,
    "verification_failed": FailureReason.NETWORK_ERROR,
    "psp_not_available": FailureReason.NETWORK_ERROR,
    "psp_app_not_available": FailureReason.NETWORK_ERROR,
    "upi_app_technical_error": FailureReason.NETWORK_ERROR,
    # Issuing bank down
    "issuer_technical_error": FailureReason.ISSUER_UNAVAILABLE,
    "bank_technical_error": FailureReason.ISSUER_UNAVAILABLE,
    "bank_not_available": FailureReason.ISSUER_UNAVAILABLE,
    "bank_cutoff_in_progress": FailureReason.ISSUER_UNAVAILABLE,
    # Limits
    "transaction_limit_exceeded": FailureReason.LIMIT_EXCEEDED,
    "transaction_daily_limit_exceeded": FailureReason.LIMIT_EXCEEDED,
    "transaction_daily_count_exceeded": FailureReason.LIMIT_EXCEEDED,
    "transaction_frequency_limit_exceeded": FailureReason.LIMIT_EXCEEDED,
    "credit_limit_exceeded": FailureReason.LIMIT_EXCEEDED,
    # Risk: Razorpay has no "fraud" reason; a failed risk check is the
    # closest documented signal, and the safety gate treats it as a hold.
    "payment_risk_check_failed": FailureReason.FRAUD_SUSPECTED,
    # Deliberately NOT mapped: "payment_failed" is documented as "no specific
    # error code received from the gateway", so it stays UNKNOWN like any
    # undocumented reason.
}


def classify_real_payment_error(payment: dict) -> tuple:
    """
    Maps a REAL Razorpay payment object's error_reason (from
    fetch_real_payment) to our FailureReason via ERROR_REASON_TO_CATEGORY.
    The error_reason string comes from Razorpay's own response, not from us.
    Anything undocumented or unspecific becomes UNKNOWN, which the agent
    escalates to support instead of guessing.

    Returns (FailureReason, raw_error_code_string).
    """
    error_reason = (payment.get("error_reason") or "").strip().lower()
    error_code = payment.get("error_code") or ""
    raw = f"{error_code} / {error_reason or 'unknown'}"
    return ERROR_REASON_TO_CATEGORY.get(error_reason, FailureReason.UNKNOWN), raw


# One documented example per category, used to label synthetic batch
# records. `raw_error_code` pairs a documented error_code with a documented
# error_reason from the sources above; descriptions paraphrase Razorpay's.
# UNKNOWN is never generated: the batch only draws documented reasons.
DOCUMENTED_ERROR_EXAMPLES: dict[FailureReason, dict] = {
    FailureReason.CARD_DECLINED: {
        "raw_error_code": "BAD_REQUEST_ERROR / card_declined",
        "description": "The card has been declined.",
    },
    FailureReason.INSUFFICIENT_FUNDS: {
        "raw_error_code": "BAD_REQUEST_ERROR / insufficient_funds",
        "description": "Insufficient balance; try another card or method.",
    },
    FailureReason.EXPIRED_CARD: {
        "raw_error_code": "BAD_REQUEST_ERROR / card_expired",
        "description": "The card has expired.",
    },
    FailureReason.BANK_TIMEOUT: {
        "raw_error_code": "BAD_REQUEST_ERROR / payment_timed_out",
        "description": "The payment was not completed in time.",
    },
    FailureReason.NETWORK_ERROR: {
        "raw_error_code": "GATEWAY_ERROR / gateway_technical_error",
        "description": "Technical error at the payment gateway; retry later.",
    },
    FailureReason.INVALID_CVV: {
        "raw_error_code": "BAD_REQUEST_ERROR / incorrect_cvv",
        "description": "The CVV entered was incorrect.",
    },
    FailureReason.INVALID_CARD_DETAILS: {
        "raw_error_code": "BAD_REQUEST_ERROR / card_number_invalid",
        "description": "The card number is invalid.",
    },
    FailureReason.AUTHENTICATION_FAILED: {
        "raw_error_code": "GATEWAY_ERROR / authentication_failed",
        "description": "3-D Secure / OTP authentication failed.",
    },
    FailureReason.PAYMENT_CANCELLED: {
        "raw_error_code": "BAD_REQUEST_ERROR / payment_cancelled",
        "description": "The customer cancelled the payment.",
    },
    FailureReason.ISSUER_UNAVAILABLE: {
        "raw_error_code": "GATEWAY_ERROR / issuer_technical_error",
        "description": "Technical error at the card issuer.",
    },
    FailureReason.LIMIT_EXCEEDED: {
        "raw_error_code": "BAD_REQUEST_ERROR / transaction_limit_exceeded",
        "description": "The card's transaction limit was exceeded.",
    },
    FailureReason.FRAUD_SUSPECTED: {
        "raw_error_code": "BAD_REQUEST_ERROR / payment_risk_check_failed",
        "description": "Declined by risk checks.",
    },
}


