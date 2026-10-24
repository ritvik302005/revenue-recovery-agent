"""
Agent loop semantics (decided 2026-10-25): an unpaid reminder link is a
failed attempt and the agent escalates; only a hand-off to support ends as
pending; once the retry budget is used, the safety gate stops the loop.
Outcome probabilities are forced to 0 or 1 so every path is deterministic.
"""
import pytest

from conftest import make_payment


@pytest.fixture()
def always(monkeypatch):
    """always(p): every simulated action succeeds with probability p."""
    import recovery_agent

    def set_probability(p):
        monkeypatch.setattr(recovery_agent, "RECOVERY_PROBABILITY", {})
        monkeypatch.setattr(recovery_agent, "DEFAULT_RECOVERY_PROBABILITY", p)
    return set_probability


def _steps(result):
    return [e.step for e in result.audit_trail]


def test_unpaid_reminder_is_a_failed_attempt_then_support_is_pending(always):
    from recovery_agent import run_recovery
    from models import FailureReason, RecoveryAction, Outcome
    always(0.0)
    r = run_recovery(make_payment(failure_reason=FailureReason.INSUFFICIENT_FUNDS))

    execs = [e for e in r.audit_trail if e.step == "execute"]
    assert "send_reminder_link" in execs[0].detail and "still_failed" in execs[0].detail
    assert r.action_taken == RecoveryAction.ESCALATE_TO_SUPPORT
    assert r.outcome == Outcome.PENDING_CUSTOMER_ACTION
    assert r.attempt_count == 2


def test_budget_exhausted_is_stopped_by_the_safety_gate(always):
    from recovery_agent import run_recovery, MAX_ATTEMPTS
    from models import FailureReason, RecoveryAction, Outcome
    always(0.0)
    r = run_recovery(make_payment(failure_reason=FailureReason.BANK_TIMEOUT))

    # retry same -> alternate method -> reminder link, then the gate blocks support.
    assert r.attempt_count == MAX_ATTEMPTS
    assert r.outcome == Outcome.STILL_FAILED
    assert r.action_taken == RecoveryAction.NO_ACTION_MAX_ATTEMPTS
    last_gate = [e for e in r.audit_trail if e.step == "safety_check"][-1]
    assert "BLOCKED" in last_gate.detail and "MAX_ATTEMPTS" in last_gate.detail
    assert _steps(r).count("execute") == MAX_ATTEMPTS


def test_the_gate_runs_before_every_execution(always):
    from recovery_agent import run_recovery
    from models import FailureReason
    always(0.0)
    steps = _steps(run_recovery(make_payment(failure_reason=FailureReason.CARD_DECLINED)))
    for i, step in enumerate(steps):
        if step == "execute":
            assert steps[i - 1] == "safety_check"


def test_success_ends_the_loop_immediately(always):
    from recovery_agent import run_recovery
    from models import FailureReason, Outcome
    always(1.0)
    r = run_recovery(make_payment(failure_reason=FailureReason.NETWORK_ERROR))
    assert r.outcome == Outcome.RECOVERED
    assert r.attempt_count == 1
    assert r.amount_recovered == r.amount


def test_replan_log_names_the_attempt(always):
    from recovery_agent import run_recovery
    from models import FailureReason
    always(0.0)
    r = run_recovery(make_payment(failure_reason=FailureReason.BANK_TIMEOUT))
    replans = [e.detail for e in r.audit_trail if e.step == "replan"]
    assert replans[0].startswith("Attempt 1 still failed")
    assert replans[1].startswith("Attempt 2 still failed")


def test_unknown_reason_goes_straight_to_support(always):
    from recovery_agent import run_recovery
    from models import FailureReason, RecoveryAction, Outcome
    always(0.0)
    r = run_recovery(make_payment(failure_reason=FailureReason.UNKNOWN))
    assert r.action_taken == RecoveryAction.ESCALATE_TO_SUPPORT
    assert r.outcome == Outcome.PENDING_CUSTOMER_ACTION
    assert r.attempt_count == 1
