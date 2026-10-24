"""
AI Revenue Recovery agent.

Flow (mirrors the sense -> propose -> safety-check -> execute -> replan
loop used in the microgrid agent):

    classify_root_cause -> select_recovery_action -> safety_check
        -> execute_action -> record_outcome -> (replan if retryable & not maxed)

Hard safety rules are enforced in code, not by the LLM, and always have
final say — this is the "bar" the track calls out (bounded, gated,
explainable actions).
"""
import os
import random
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from models import (
    PaymentRecord, FailureReason, RecoveryAction, Outcome,
    AuditLogEntry, RecoveryResult,
)

MAX_ATTEMPTS = 3
NO_RETRY_REASONS = {FailureReason.FRAUD_SUSPECTED}

# Deterministic-ish recovery probability per failure reason x action, used to
# simulate real-world outcomes against Razorpay test-mode payment attempts.
RECOVERY_PROBABILITY = {
    (FailureReason.CARD_DECLINED, RecoveryAction.SUGGEST_ALTERNATE_METHOD): 0.55,
    (FailureReason.CARD_DECLINED, RecoveryAction.RETRY_WITH_DELAY): 0.20,
    (FailureReason.INSUFFICIENT_FUNDS, RecoveryAction.SEND_REMINDER_LINK): 0.40,
    (FailureReason.INSUFFICIENT_FUNDS, RecoveryAction.RETRY_WITH_DELAY): 0.15,
    (FailureReason.BANK_TIMEOUT, RecoveryAction.RETRY_SAME_METHOD): 0.65,
    (FailureReason.NETWORK_ERROR, RecoveryAction.RETRY_SAME_METHOD): 0.70,
    (FailureReason.EXPIRED_CARD, RecoveryAction.SUGGEST_ALTERNATE_METHOD): 0.60,
    (FailureReason.INVALID_CVV, RecoveryAction.RETRY_SAME_METHOD): 0.35,
    (FailureReason.ISSUER_UNAVAILABLE, RecoveryAction.RETRY_WITH_DELAY): 0.45,
    (FailureReason.LIMIT_EXCEEDED, RecoveryAction.SUGGEST_ALTERNATE_METHOD): 0.50,
}


class AgentState(TypedDict):
    payment: PaymentRecord
    audit_trail: list[AuditLogEntry]
    action: Optional[RecoveryAction]
    outcome: Optional[Outcome]
    amount_recovered: int
    reasoning: str
    done: bool


def _log(state: AgentState, step: str, detail: str, data: dict | None = None):
    state["audit_trail"].append(
        AuditLogEntry(payment_id=state["payment"].payment_id, step=step, detail=detail, data=data)
    )


def classify_root_cause(state: AgentState) -> AgentState:
    """In this simulation the failure reason is already tagged on the
    record (as it would be from Razorpay's error_reason field on a
    payment.failed webhook). This node is where an LLM call would sit
    if classifying from free-text bank error messages instead."""
    p = state["payment"]
    _log(state, "classify", f"Root cause identified as '{p.failure_reason.value}' "
                             f"from payment gateway error code (method: {p.original_method}).")
    return state


def select_recovery_action(state: AgentState) -> AgentState:
    p = state["payment"]
    reason = p.failure_reason

    mapping = {
        FailureReason.CARD_DECLINED: RecoveryAction.SUGGEST_ALTERNATE_METHOD,
        FailureReason.INSUFFICIENT_FUNDS: RecoveryAction.SEND_REMINDER_LINK,
        FailureReason.BANK_TIMEOUT: RecoveryAction.RETRY_SAME_METHOD,
        FailureReason.NETWORK_ERROR: RecoveryAction.RETRY_SAME_METHOD,
        FailureReason.EXPIRED_CARD: RecoveryAction.SUGGEST_ALTERNATE_METHOD,
        FailureReason.INVALID_CVV: RecoveryAction.RETRY_SAME_METHOD,
        FailureReason.ISSUER_UNAVAILABLE: RecoveryAction.RETRY_WITH_DELAY,
        FailureReason.LIMIT_EXCEEDED: RecoveryAction.SUGGEST_ALTERNATE_METHOD,
        FailureReason.INVALID_CARD_DETAILS: RecoveryAction.RETRY_SAME_METHOD,     # re-enter details
        FailureReason.AUTHENTICATION_FAILED: RecoveryAction.RETRY_SAME_METHOD,    # redo OTP / 3-D Secure
        FailureReason.PAYMENT_CANCELLED: RecoveryAction.SEND_REMINDER_LINK,       # customer walked away
        FailureReason.FRAUD_SUSPECTED: RecoveryAction.NO_ACTION_FRAUD_HOLD,
        FailureReason.UNKNOWN: RecoveryAction.ESCALATE_TO_SUPPORT,                # don't guess
    }
    action = mapping.get(reason, RecoveryAction.ESCALATE_TO_SUPPORT)
    state["action"] = action
    _log(state, "select_action",
         f"Selected '{action.value}' as the recovery strategy for '{reason.value}'.")
    return state


def safety_check(state: AgentState) -> AgentState:
    """Hard-coded rules that override whatever action was proposed.
    This is the non-negotiable gate, same role as the safety-floor
    override in the microgrid agent."""
    p = state["payment"]

    if p.failure_reason in NO_RETRY_REASONS:
        state["action"] = RecoveryAction.NO_ACTION_FRAUD_HOLD
        state["outcome"] = Outcome.HELD_NO_ACTION
        state["done"] = True
        _log(state, "safety_check",
             "BLOCKED: failure reason is fraud-suspected. Hard rule forbids any "
             "retry or customer contact; escalated to manual review only.")
        return state

    if p.attempt_count >= MAX_ATTEMPTS:
        state["action"] = RecoveryAction.NO_ACTION_MAX_ATTEMPTS
        state["outcome"] = Outcome.STILL_FAILED
        state["done"] = True
        _log(state, "safety_check",
             f"BLOCKED: attempt_count ({p.attempt_count}) has reached MAX_ATTEMPTS "
             f"({MAX_ATTEMPTS}). Stopping to avoid spamming customer / issuer.")
        return state

    _log(state, "safety_check", "Passed: within retry budget, no fraud flag. Proceeding to execute.")
    state["done"] = False
    return state


def execute_action(state: AgentState) -> AgentState:
    if state["done"]:
        return state  # blocked by safety_check

    p = state["payment"]
    action = state["action"]
    p.attempt_count += 1

    key = (p.failure_reason, action)
    prob = RECOVERY_PROBABILITY.get(key, 0.25)
    rng = random.Random(f"{p.payment_id}-{p.attempt_count}")
    success = rng.random() < prob

    if action in (RecoveryAction.SEND_REMINDER_LINK, RecoveryAction.ESCALATE_TO_SUPPORT) and not success:
        state["outcome"] = Outcome.PENDING_CUSTOMER_ACTION
    elif success:
        state["outcome"] = Outcome.RECOVERED
        state["amount_recovered"] = p.amount
    else:
        state["outcome"] = Outcome.STILL_FAILED

    _log(state, "execute",
         f"Executed '{action.value}' (attempt {p.attempt_count}/{MAX_ATTEMPTS}) — "
         f"simulated recovery outcome. Result: {state['outcome'].value}.",
         data={"amount": p.amount, "attempt": p.attempt_count})

    state["done"] = state["outcome"] in (Outcome.RECOVERED,) or p.attempt_count >= MAX_ATTEMPTS
    return state


def should_replan(state: AgentState) -> str:
    """Replan loop: if still failed and retries remain and it's a
    retryable outcome, loop back to action selection (e.g. escalate
    tier), else end."""
    if state["done"]:
        return "end"
    if state["outcome"] == Outcome.STILL_FAILED and state["payment"].attempt_count < MAX_ATTEMPTS:
        return "replan"
    return "end"


def escalate_action(state: AgentState) -> AgentState:
    """On replan, escalate to a stronger action rather than repeating
    the same one blindly."""
    escalation = {
        RecoveryAction.RETRY_SAME_METHOD: RecoveryAction.SUGGEST_ALTERNATE_METHOD,
        RecoveryAction.SUGGEST_ALTERNATE_METHOD: RecoveryAction.SEND_REMINDER_LINK,
        RecoveryAction.SEND_REMINDER_LINK: RecoveryAction.ESCALATE_TO_SUPPORT,
        RecoveryAction.RETRY_WITH_DELAY: RecoveryAction.SUGGEST_ALTERNATE_METHOD,
    }
    prev = state["action"]
    state["action"] = escalation.get(prev, RecoveryAction.ESCALATE_TO_SUPPORT)
    _log(state, "replan",
         f"First attempt still failed. Escalating strategy from '{prev.value}' to "
         f"'{state['action'].value}'.")
    return state


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_root_cause)
    graph.add_node("select_action", select_recovery_action)
    graph.add_node("safety_check", safety_check)
    graph.add_node("execute", execute_action)
    graph.add_node("escalate", escalate_action)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "select_action")
    graph.add_edge("select_action", "safety_check")
    graph.add_edge("safety_check", "execute")
    graph.add_conditional_edges("execute", should_replan, {"replan": "escalate", "end": END})
    graph.add_edge("escalate", "safety_check")

    return graph.compile()


_compiled_graph = build_graph()


def run_recovery(payment: PaymentRecord) -> RecoveryResult:
    initial_state: AgentState = {
        "payment": payment,
        "audit_trail": [],
        "action": None,
        "outcome": None,
        "amount_recovered": 0,
        "reasoning": "",
        "done": False,
    }
    final_state = _compiled_graph.invoke(initial_state)

    reasoning = " -> ".join(f"[{e.step}] {e.detail}" for e in final_state["audit_trail"])

    return RecoveryResult(
        payment_id=payment.payment_id,
        order_id=payment.order_id,
        razorpay_order_id=payment.razorpay_order_id,
        razorpay_source=payment.razorpay_source,
        amount=payment.amount,
        failure_reason=payment.failure_reason,
        raw_error_code=payment.raw_error_code,
        action_taken=final_state["action"],
        outcome=final_state["outcome"],
        outcome_is_simulated=True,  # recovery outcome is never real — see razorpay_client.py docstring
        attempt_count=payment.attempt_count,
        amount_recovered=final_state["amount_recovered"],
        reasoning=reasoning,
        audit_trail=final_state["audit_trail"],
    )
