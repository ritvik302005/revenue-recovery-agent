"""
What the agent actually does once an action passes the safety gate (P7).

`plan_execution` turns an action into a concrete plan: open a payment
request for the customer now, open one after a delay, open one with the
failed method hidden, send a reminder, or open a support case instead of
asking for money. It is a pure function, shared by the live demo (which
then carries the plan out: request, outbox message, support case) and the
batch (which records the same plan in its audit trail without calling
Razorpay; only the payment outcome there is simulated).
"""
import os
from dataclasses import dataclass, asdict
from typing import Optional

from models import RecoveryAction

# Demo value: real systems wait minutes to hours before retrying.
RECOVERY_DELAY_SECONDS = int(os.environ.get("RECOVERY_DELAY_SECONDS", 30))
# How long a recovery request stays payable before it counts as unpaid.
RECOVERY_REQUEST_TTL_SECONDS = int(os.environ.get("RECOVERY_REQUEST_TTL_SECONDS", 1800))

MERCHANT_NAME = "Revenue Recovery Demo"

METHOD_NAMES = {
    "card": "card", "upi": "UPI", "netbanking": "netbanking", "wallet": "wallet",
    "emi": "EMI", "paylater": "pay later",
}


@dataclass
class ExecutionPlan:
    action: str
    kind: str                       # "payment_request" | "support_case" | "none"
    delay_seconds: int = 0
    excluded_method: Optional[str] = None
    customer_message: Optional[str] = None   # what the customer gets (SMS/email in production)
    summary: str = ""                         # one line for the audit trail

    def to_dict(self) -> dict:
        return asdict(self)


def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


def plan_execution(action: RecoveryAction, amount: int, failed_method: Optional[str] = None) -> ExecutionPlan:
    """The concrete step for an approved action. `failed_method` is the
    method of the payment that failed (Razorpay's payment.method)."""
    action = RecoveryAction(action)
    what = f"your payment of {_rupees(amount)} to {MERCHANT_NAME}"

    if action == RecoveryAction.RETRY_SAME_METHOD:
        return ExecutionPlan(
            action=action.value, kind="payment_request",
            customer_message=f"Sorry, {what} didn't go through. You can try again here: {{link}}",
            summary="Opened a recovery request the customer can pay now, with any method.")

    if action == RecoveryAction.RETRY_WITH_DELAY:
        return ExecutionPlan(
            action=action.value, kind="payment_request", delay_seconds=RECOVERY_DELAY_SECONDS,
            customer_message=f"Your bank couldn't take {what} just now. You can try again "
                             f"in a few minutes here: {{link}}",
            summary=f"Scheduled a recovery request, payable after {RECOVERY_DELAY_SECONDS} s "
                    f"(shortened for the demo; real systems wait minutes to hours).")

    if action == RecoveryAction.SUGGEST_ALTERNATE_METHOD:
        method = failed_method if failed_method in METHOD_NAMES else None
        hidden = f" Your {METHOD_NAMES[method]} isn't offered this time." if method else ""
        return ExecutionPlan(
            action=action.value, kind="payment_request", excluded_method=method,
            customer_message=f"{what[0].upper()}{what[1:]} didn't go through. Please try a different "
                             f"payment method here: {{link}}.{hidden}",
            summary=(f"Opened a recovery request with '{method}' hidden, so the customer pays another way."
                     if method else "Opened a recovery request suggesting another payment method "
                                    "(the failed method wasn't known, so none is hidden)."))

    if action == RecoveryAction.SEND_REMINDER_LINK:
        return ExecutionPlan(
            action=action.value, kind="payment_request",
            customer_message=f"Reminder: {what} is still pending. Pay here: {{link}}",
            summary="Sent the customer a reminder with a payment link.")

    if action == RecoveryAction.ESCALATE_TO_SUPPORT:
        return ExecutionPlan(
            action=action.value, kind="support_case",
            summary="Opened a support case; no payment request is sent to the customer.")

    return ExecutionPlan(action=action.value, kind="none", summary="No action: the safety gate holds this payment.")
