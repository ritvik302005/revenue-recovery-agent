"""
The safety gate is the "bar" this whole project is built around: two
hard rules that must never be bypassed, regardless of what the LLM/
strategy-selection layer proposes.
"""
import pytest

from conftest import make_payment


def test_fraud_suspected_always_blocks_recovery():
    """A fraud-suspected payment must never be retried or contacted —
    only held for manual review, on the very first attempt."""
    from recovery_agent import run_recovery
    from models import FailureReason, RecoveryAction, Outcome

    payment = make_payment(failure_reason=FailureReason.FRAUD_SUSPECTED, attempt_count=0)
    result = run_recovery(payment)

    assert result.action_taken == RecoveryAction.NO_ACTION_FRAUD_HOLD
    assert result.outcome == Outcome.HELD_NO_ACTION
    assert result.amount_recovered == 0

    safety_entries = [e for e in result.audit_trail if e.step == "safety_check"]
    assert len(safety_entries) == 1
    assert "BLOCKED" in safety_entries[0].detail
    assert "fraud" in safety_entries[0].detail.lower()


@pytest.mark.parametrize("failure_reason", [
    "card_declined", "insufficient_funds", "bank_timeout", "network_error",
    "expired_card", "invalid_cvv", "issuer_unavailable", "limit_exceeded",
])
def test_fraud_block_is_reason_specific_not_universal(failure_reason):
    """Sanity check the other side of the same rule: non-fraud reasons
    are NOT held — proves the fraud block is a targeted rule, not an
    accidental blanket stop."""
    from recovery_agent import run_recovery
    from models import FailureReason, Outcome

    payment = make_payment(failure_reason=FailureReason(failure_reason), attempt_count=0)
    result = run_recovery(payment)

    assert result.outcome != Outcome.HELD_NO_ACTION


def test_fraud_block_never_increments_attempt_count():
    """Fraud hold must block before execution — it never even counts
    as an attempt, since nothing was actually tried."""
    from recovery_agent import run_recovery
    from models import FailureReason, Outcome

    payment = make_payment(failure_reason=FailureReason.FRAUD_SUSPECTED, attempt_count=0)
    result = run_recovery(payment)
    assert result.attempt_count == 0
    assert result.outcome == Outcome.HELD_NO_ACTION


@pytest.mark.parametrize("prior_attempts", [0, 1, 2, 3, 5])
def test_fraud_block_holds_regardless_of_attempt_history(prior_attempts):
    """Fraud is an absolute block — it must fire the same way whether
    this is the first attempt or the payment already has a long retry
    history. Attempt count must never override it."""
    from recovery_agent import run_recovery
    from models import FailureReason, RecoveryAction, Outcome

    payment = make_payment(failure_reason=FailureReason.FRAUD_SUSPECTED, attempt_count=prior_attempts)
    result = run_recovery(payment)
    assert result.action_taken == RecoveryAction.NO_ACTION_FRAUD_HOLD
    assert result.outcome == Outcome.HELD_NO_ACTION


def test_max_attempts_always_blocks_further_recovery():
    """Once a payment has already reached MAX_ATTEMPTS, the agent must
    refuse to try again — no matter how promising the strategy looks."""
    from recovery_agent import run_recovery, MAX_ATTEMPTS
    from models import FailureReason, RecoveryAction, Outcome

    payment = make_payment(failure_reason=FailureReason.CARD_DECLINED, attempt_count=MAX_ATTEMPTS)
    result = run_recovery(payment)

    assert result.action_taken == RecoveryAction.NO_ACTION_MAX_ATTEMPTS
    assert result.outcome == Outcome.STILL_FAILED
    assert result.amount_recovered == 0

    safety_entries = [e for e in result.audit_trail if e.step == "safety_check"]
    assert len(safety_entries) == 1
    assert "BLOCKED" in safety_entries[0].detail
    assert "MAX_ATTEMPTS" in safety_entries[0].detail


def test_max_attempts_blocks_beyond_the_limit_too():
    """Defensive: a record that's already exceeded the cap (shouldn't
    normally happen, but data can be messy) still gets blocked, not
    treated as "under budget" by an off-by-one comparison."""
    from recovery_agent import run_recovery, MAX_ATTEMPTS
    from models import FailureReason, Outcome

    payment = make_payment(failure_reason=FailureReason.CARD_DECLINED, attempt_count=MAX_ATTEMPTS + 5)
    result = run_recovery(payment)
    assert result.outcome == Outcome.STILL_FAILED
    assert result.amount_recovered == 0


def test_within_budget_is_not_blocked():
    """Sanity check the other side: attempt_count below the cap must
    be allowed to proceed to execution (not itself blocked)."""
    from recovery_agent import run_recovery, MAX_ATTEMPTS
    from models import FailureReason

    payment = make_payment(failure_reason=FailureReason.CARD_DECLINED, attempt_count=MAX_ATTEMPTS - 1)
    result = run_recovery(payment)

    safety_entries = [e for e in result.audit_trail if e.step == "safety_check"]
    assert len(safety_entries) >= 1
    assert "Passed" in safety_entries[0].detail or "BLOCKED" not in safety_entries[0].detail
