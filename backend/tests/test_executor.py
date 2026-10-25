"""
The executor (P7-1, P7-6): every approved action becomes a concrete plan,
shared by the live demo and the batch; failed actions escalate in a fixed order.
"""
import pytest

import executor
from conftest import make_payment
from executor import plan_execution
from models import FailureReason, RecoveryAction
from recovery_agent import next_action, run_recovery


@pytest.mark.parametrize("action, kind, delayed, hides", [
    (RecoveryAction.RETRY_SAME_METHOD, "payment_request", False, False),
    (RecoveryAction.RETRY_WITH_DELAY, "payment_request", True, False),
    (RecoveryAction.SUGGEST_ALTERNATE_METHOD, "payment_request", False, True),
    (RecoveryAction.SEND_REMINDER_LINK, "payment_request", False, False),
    (RecoveryAction.ESCALATE_TO_SUPPORT, "support_case", False, False),
    (RecoveryAction.NO_ACTION_FRAUD_HOLD, "none", False, False),
    (RecoveryAction.NO_ACTION_MAX_ATTEMPTS, "none", False, False),
])
def test_every_action_has_a_concrete_plan(action, kind, delayed, hides):
    plan = plan_execution(action, 49900, "card")
    assert plan.kind == kind
    assert (plan.delay_seconds > 0) is delayed
    assert (plan.excluded_method == "card") is hides
    assert plan.summary
    if kind == "payment_request":
        assert "{link}" in plan.customer_message and "₹499.00" in plan.customer_message
    else:
        assert plan.customer_message is None        # nothing is sent to the customer


def test_delay_comes_from_configuration(monkeypatch):
    monkeypatch.setattr(executor, "RECOVERY_DELAY_SECONDS", 7)
    assert plan_execution(RecoveryAction.RETRY_WITH_DELAY, 1000).delay_seconds == 7


def test_alternate_method_with_an_unknown_method_hides_nothing():
    plan = plan_execution(RecoveryAction.SUGGEST_ALTERNATE_METHOD, 1000, None)
    assert plan.excluded_method is None
    assert "none is hidden" in plan.summary


def test_escalation_order():
    chain, action = [], RecoveryAction.RETRY_SAME_METHOD
    for _ in range(3):
        action = next_action(action)
        chain.append(action)
    assert chain == [RecoveryAction.SUGGEST_ALTERNATE_METHOD, RecoveryAction.SEND_REMINDER_LINK,
                     RecoveryAction.ESCALATE_TO_SUPPORT]
    assert next_action(RecoveryAction.RETRY_WITH_DELAY) == RecoveryAction.SUGGEST_ALTERNATE_METHOD


def test_batch_records_the_same_plan_it_would_execute():
    result = run_recovery(make_payment(failure_reason=FailureReason.CARD_DECLINED, original_method="upi"))
    executes = [e for e in result.audit_trail if e.step == "execute"]
    first = executes[0]
    assert first.data["plan"]["action"] == "suggest_alternate_method"
    assert first.data["plan"]["excluded_method"] == "upi"
    assert "hidden" in first.detail and "Simulated recovery outcome" in first.detail
