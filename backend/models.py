"""
Core data models for the AI Revenue Recovery agent.
"""
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class FailureReason(str, Enum):
    """Our failure categories. Razorpay's documented error_reason values
    map onto these in razorpay_client.ERROR_REASON_TO_CATEGORY."""
    CARD_DECLINED = "card_declined"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    EXPIRED_CARD = "expired_card"
    BANK_TIMEOUT = "bank_timeout"
    NETWORK_ERROR = "network_error"
    INVALID_CVV = "invalid_cvv"
    INVALID_CARD_DETAILS = "invalid_card_details"
    AUTHENTICATION_FAILED = "authentication_failed"  # OTP / 3-D Secure / PIN
    PAYMENT_CANCELLED = "payment_cancelled"          # customer cancelled
    FRAUD_SUSPECTED = "fraud_suspected"          # no-retry category (Razorpay risk check failed)
    ISSUER_UNAVAILABLE = "issuer_unavailable"
    LIMIT_EXCEEDED = "limit_exceeded"
    UNKNOWN = "unknown"                          # undocumented or unspecific reason: escalate, don't guess


class RecoveryAction(str, Enum):
    RETRY_SAME_METHOD = "retry_same_method"
    RETRY_WITH_DELAY = "retry_with_delay"
    SUGGEST_ALTERNATE_METHOD = "suggest_alternate_method"
    SEND_REMINDER_LINK = "send_reminder_link"
    ESCALATE_TO_SUPPORT = "escalate_to_support"
    NO_ACTION_FRAUD_HOLD = "no_action_fraud_hold"
    NO_ACTION_MAX_ATTEMPTS = "no_action_max_attempts"


class Outcome(str, Enum):
    RECOVERED = "recovered"
    STILL_FAILED = "still_failed"
    PENDING_CUSTOMER_ACTION = "pending_customer_action"
    HELD_NO_ACTION = "held_no_action"


class RazorpaySource(str, Enum):
    """Where a batch record's ORDER came from. In both cases the failure
    reason is synthetic (a documented Razorpay code assigned by the
    generator) and the recovery outcome is simulated."""
    RAZORPAY_TEST_ORDER = "razorpay_test_order"   # a real order created via Razorpay's test-mode Orders API
    LOCAL_ORDER = "local_order"                   # no Razorpay call; locally generated order id


class PaymentRecord(BaseModel):
    """
    A payment the recovery agent will act on.

    razorpay_order_id / razorpay_source / raw_error_code are the ONLY
    fields that should ever be populated from a genuine Razorpay API
    response. Nothing about recovery outcome belongs on this model —
    see SimulatedRecoveryOutcome in recovery_agent results.
    """
    payment_id: str = Field(default_factory=lambda: f"pay_{uuid.uuid4().hex[:14]}")
    order_id: str = Field(default_factory=lambda: f"order_{uuid.uuid4().hex[:14]}")
    razorpay_order_id: Optional[str] = None      # populated only by a real Orders API call
    razorpay_source: RazorpaySource = RazorpaySource.LOCAL_ORDER
    amount: int  # in paise, like Razorpay
    currency: str = "INR"
    customer_email: str
    customer_contact: str
    original_method: str  # card, upi, netbanking, wallet
    failure_reason: FailureReason
    raw_error_code: Optional[str] = None   # Razorpay's actual error code string, when known
    attempt_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payment_id: str
    step: str                      # e.g. "classify", "select_action", "safety_check", "execute"
    detail: str                    # human-readable reasoning
    data: Optional[dict] = None


class LiveDemoStage(str, Enum):
    """Live-demo session stages. They only move forward:

    order_created -> failure_recorded -> recovery_order_created -> recovered
                  -> held (safety gate)                         -> recovery_failed
                                                                     -> recovery_order_created (retry)
    """
    ORDER_CREATED = "order_created"
    FAILURE_RECORDED = "failure_recorded"
    HELD = "held"                                  # safety gate blocked recovery; final
    RECOVERY_ORDER_CREATED = "recovery_order_created"
    RECOVERED = "recovered"                        # final
    RECOVERY_FAILED = "recovery_failed"            # a new recovery order may follow


class LiveDemoResult(BaseModel):
    """
    Result of a single live-demo Checkout-driven payment. Unlike
    RecoveryResult (batch mode), everything here — including the
    recovery outcome — comes from a real human clicking through
    Razorpay's Checkout with real test instruments. outcome_is_simulated
    is always False here; that's the whole point of this path.
    """
    original_order_id: str
    original_payment_id: str
    recovery_order_id: Optional[str] = None
    recovery_payment_id: Optional[str] = None
    amount: int
    failure_reason: FailureReason
    raw_error_code: str
    recommended_action: RecoveryAction
    safety_check_passed: bool
    recovery_outcome: Optional[Outcome] = None
    outcome_is_simulated: bool = False  # this path is genuinely real end-to-end
    amount_recovered: int = 0
    audit_trail: list[AuditLogEntry] = Field(default_factory=list)


class RecoveryResult(BaseModel):
    payment_id: str
    order_id: str
    razorpay_order_id: Optional[str] = None
    razorpay_source: RazorpaySource
    amount: int
    failure_reason: FailureReason
    raw_error_code: Optional[str] = None
    action_taken: RecoveryAction
    outcome: Outcome
    outcome_is_simulated: bool = True   # recovery outcome is ALWAYS simulated — see note above
    attempt_count: int
    amount_recovered: int = 0     # paise; simulated
    reasoning: str
    audit_trail: list[AuditLogEntry] = Field(default_factory=list)
