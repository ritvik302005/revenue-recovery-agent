"""
FastAPI application for the AI Revenue Recovery agent.

Endpoints (full table in docs/ARCHITECTURE.md):
  POST /api/session         - short-lived token for the endpoints that act
  POST /api/batch/run       - generate a batch and run the recovery agent on it
  GET  /api/batch/results   - fetch the last run's results
  GET  /api/batch/metrics   - summary metrics, split real vs simulated
  GET  /api/evaluation      - the published multi-seed evaluation
  GET  /api/showcase/case   - one real recorded case for the landing page
  GET  /api/health          - basic health check
  /api/live-demo/*          - the real Razorpay Test Mode flow (operator side)
  /api/recover/{token}      - the customer's recovery request (P7)
  POST /api/webhooks/razorpay - signed Razorpay events
"""
from fastapi import FastAPI, Query, Path, HTTPException, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Optional
import json
import math
import os
import secrets
import time

from models import (RazorpaySource, Outcome, LiveDemoResult, AuditLogEntry, RecoveryResult, LiveDemoStage,
                    FailureReason, RecoveryAction)
from simulate_batch import generate_batch, MAX_LIVE_ORDERS_PER_BATCH
from recovery_agent import run_recovery, select_recovery_action, safety_check, next_action, AgentState, MAX_ATTEMPTS
from executor import plan_execution, MERCHANT_NAME, RECOVERY_REQUEST_TTL_SECONDS
from razorpay_client import (
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    create_real_order, fetch_real_payment, classify_real_payment_error,
    verify_checkout_signature, verify_webhook_signature, RazorpayNotConfigured,
    webhook_configured as razorpay_webhook_configured,
    key_mode as razorpay_key_mode, HEALTH_KEY as RAZORPAY_HEALTH_KEY,
)
from pydantic import BaseModel, Field, ValidationError
import logging
import uuid
import razorpay.errors
import access
import storage

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Revenue Recovery Agent")

# ---- CORS: allow only known frontend origin(s), not "*" ----
# Set ALLOWED_ORIGINS in the environment to a comma-separated list for
# production, e.g. "https://app.example.com,https://staging.example.com".
# Falls back to local Vite dev origins when unset, for local development.
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = (
    [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    if _allowed_origins_env
    else ["http://localhost:5173", "http://localhost:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-Token"],
)

# ---- Access and rate limits (P5-1, P5-2): see access.py ----
# Every endpoint that calls Razorpay or does heavy work needs a session
# token from POST /api/session and is rate limited per client IP.
limit_sessions = Depends(access.rate_limit("session", 10))
limit_orders = Depends(access.rate_limit("orders", 10))
limit_reports = Depends(access.rate_limit("reports", 30))
limit_batches = Depends(access.rate_limit("batches", 10))


def _require_owner(record: dict, token: str, order_id: str) -> None:
    """A live-demo session can only be driven by the token that created it."""
    if record.get("owner") != access.owner_of(token):
        raise HTTPException(status_code=403, detail=f"Order '{order_id}' belongs to a different session.")


# ---- Razorpay errors shown to the browser ----
# Raw exception text can carry internal details (hosts, stack context), so
# it goes to the server log only. Razorpay's own error description (a
# BadRequestError, e.g. "The id provided does not exist") is safe and
# useful, so that one is passed through.
def _razorpay_error(action: str, e: Exception) -> HTTPException:
    logger.warning("Razorpay call failed (%s): %r", action, e)
    if isinstance(e, RazorpayNotConfigured):
        return HTTPException(status_code=503, detail="Razorpay test keys aren't configured on this server, so the live demo is unavailable.")
    if isinstance(e, razorpay.errors.BadRequestError) and str(e):
        return HTTPException(status_code=502, detail=f"Could not {action}. Razorpay said: {e}")
    return HTTPException(status_code=502, detail=f"Could not {action}: Razorpay is unreachable or returned an error. Try again shortly.")


# The last batch run, persisted via storage (SQLite, or Redis if configured).
BATCH_RESULTS_KEY = "batch:last_results"
DEFAULT_BATCH_SEED = 42


def _save_last_results(results: list, seed: int) -> None:
    storage.set_value(BATCH_RESULTS_KEY, {"seed": seed, "items": [r.model_dump(mode="json") for r in results]})


def _last_batch_seed() -> Optional[int]:
    raw = storage.get_value(BATCH_RESULTS_KEY)
    return raw.get("seed") if raw else None


def _load_last_results() -> list:
    raw = storage.get_value(BATCH_RESULTS_KEY)
    if not raw:
        return []
    try:
        return [RecoveryResult(**item) for item in raw["items"]]
    except ValidationError:
        # Saved by an older version (e.g. before the provenance values were
        # renamed). Treat it as no batch rather than failing every request.
        logger.warning("Stored batch results don't match the current schema; ignoring them. Run a new batch.")
        return []


@app.get("/api/health")
def health():
    """What the server actually knows. Razorpay reachability comes from the
    latest real calls (recorded by razorpay_client), not from a probe."""
    calls = storage.get_value(RAZORPAY_HEALTH_KEY) or {}
    mode = razorpay_key_mode()
    return {
        "status": "ok",
        "razorpay_keys_configured": bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET) and mode == "test",
        "razorpay_key_mode": mode,
        "storage_backend": storage.backend_name(),
        "razorpay_last_success_at": calls.get("last_success_at"),
        "razorpay_last_failure_at": calls.get("last_failure_at"),
        "razorpay_last_failure_kind": calls.get("last_failure_kind"),
    }


@app.post("/api/session", dependencies=[limit_sessions])
def create_session():
    """A short-lived token for the endpoints below (X-Session-Token)."""
    return access.issue_session()


@app.post("/api/batch/run", dependencies=[limit_batches])
def run_batch(n: int = Query(60, ge=1, le=500), try_live_orders: bool = Query(False),
              seed: int = Query(DEFAULT_BATCH_SEED, ge=0, le=2**31 - 1),
              token: str = Depends(access.require_session)):
    """Same seed -> same synthetic batch and same simulated outcomes.
    try_live_orders (off by default) creates real test orders for at most
    MAX_LIVE_ORDERS_PER_BATCH records, within the session's and today's
    order budget, and stops at the first failure."""
    live_slots = access.reserve_orders(token, MAX_LIVE_ORDERS_PER_BATCH) if try_live_orders else 0
    batch = generate_batch(n=n, seed=seed, try_live_orders=live_slots > 0, max_live_orders=live_slots)
    results = [run_recovery(p) for p in batch]
    _save_last_results(results, seed)
    return {"count": len(results), "seed": seed, "results": [r.model_dump(mode="json") for r in results]}


@app.get("/api/batch/results")
def get_results():
    results = _load_last_results()
    return {"count": len(results), "seed": _last_batch_seed() if results else None,
            "results": [r.model_dump(mode="json") for r in results]}


@app.get("/api/batch/metrics")
def get_metrics():
    results = _load_last_results()
    if not results:
        raise HTTPException(status_code=404, detail="No batch has been run yet. POST /api/batch/run first.")

    total = len(results)

    razorpay_order_count = sum(1 for r in results if r.razorpay_source == RazorpaySource.RAZORPAY_TEST_ORDER)
    local_order_count = total - razorpay_order_count

    recovered = [r for r in results if r.outcome == Outcome.RECOVERED]
    still_failed = [r for r in results if r.outcome == Outcome.STILL_FAILED]
    pending = [r for r in results if r.outcome == Outcome.PENDING_CUSTOMER_ACTION]
    held = [r for r in results if r.outcome == Outcome.HELD_NO_ACTION]

    total_at_risk = sum(r.amount for r in results)
    total_recovered = sum(r.amount_recovered for r in results)

    by_reason = {}
    for r in results:
        key = r.failure_reason.value
        by_reason.setdefault(key, {"count": 0, "recovered": 0})
        by_reason[key]["count"] += 1
        if r.outcome == Outcome.RECOVERED:
            by_reason[key]["recovered"] += 1

    return {
        "razorpay_data_provenance": {
            "note": "These counts describe where each record's order came from: a real "
                     "Razorpay test-mode order, or a locally generated order id. Failure reasons "
                     "are synthetic in both cases. They do NOT describe recovery outcomes, which "
                     "are always simulated.",
            "razorpay_test_orders": razorpay_order_count,
            "local_orders": local_order_count,
        },
        "simulated_recovery_summary": {
            "note": "Recovery outcomes below are simulated — Razorpay test mode cannot "
                     "headlessly simulate a customer successfully retrying a payment.",
            "batch_size": total,
            "seed": _last_batch_seed(),
            "recovered": len(recovered),
            "still_failed": len(still_failed),
            "pending_customer_action": len(pending),
            "held_no_action_fraud": len(held),
            "recovery_rate_pct": round(len(recovered) / total * 100, 1) if total else 0,
            "total_amount_at_risk_inr": round(total_at_risk / 100, 2),
            "total_amount_recovered_inr": round(total_recovered / 100, 2),
        },
        "breakdown_by_failure_reason": by_reason,
    }


LIVE_DEMO_KEY_PREFIX = "live_demo:"

# Razorpay ids are a fixed prefix plus letters and digits. Validated before
# any id reaches the SDK (where it becomes part of a URL path), so values
# like "pay_../orders" are rejected with 422 and never sent to Razorpay.
ORDER_ID_PATTERN = r"^order_[A-Za-z0-9]{1,40}$"
PAYMENT_ID_PATTERN = r"^pay_[A-Za-z0-9]{1,40}$"


def _get_demo_record(order_id: str) -> Optional[dict]:
    return storage.get_value(LIVE_DEMO_KEY_PREFIX + order_id)


def _set_demo_record(order_id: str, data: dict) -> None:
    storage.set_value(LIVE_DEMO_KEY_PREFIX + order_id, data, ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)


def _require_stage(record: Optional[dict], order_id: str, allowed: set) -> dict:
    """404 for an unknown session, 409 if it isn't at one of the allowed stages."""
    if not record:
        raise HTTPException(status_code=404, detail=f"Unknown order_id '{order_id}'. Call /create-order first.")
    if record.get("stage") not in {s.value for s in allowed}:
        raise HTTPException(
            status_code=409,
            detail=f"Order '{order_id}' is at stage '{record.get('stage')}'; this step needs "
                   f"{' or '.join(sorted(s.value for s in allowed))}.",
        )
    return record


# ---- Multi-seed evaluation (P4-4): the only source of headline recovery numbers ----
EVALUATION_PATH = os.environ.get(
    "EVALUATION_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation", "batch_eval.json"))


@app.get("/api/evaluation")
def evaluation():
    """The committed result of evaluate_batch.py: many seeded batch runs,
    summarised with uncertainty. It is a simulation and says so."""
    try:
        with open(EVALUATION_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No evaluation yet. Run `python evaluate_batch.py` in backend/.")


# ---- Showcase case: one real recorded case for the landing page ----
# The latest live-demo session that reached a result is kept here with no
# expiry (sessions themselves expire). Nothing in it is invented: every
# field comes from the session, i.e. from Razorpay and the agent's run.
SHOWCASE_LIVE_KEY = "showcase:latest_live_case"


def _record_showcase(order_id: str, record: dict) -> None:
    result = record.get("result") or {}
    audit_trail = record.get("audit_trail", [])
    storage.set_value(SHOWCASE_LIVE_KEY, {
        "kind": "live_demo",
        "recorded_at": audit_trail[-1]["timestamp"] if audit_trail else None,
        "order_id": order_id,
        "payment_id": record.get("original_payment_id"),
        "recovery_order_id": result.get("recovery_order_id"),
        "recovery_payment_id": result.get("recovery_payment_id"),
        "amount": record.get("amount"),
        "failure_reason": record.get("failure_reason"),
        "raw_error_code": record.get("raw_error_code"),
        "action": record.get("recommended_action"),
        "safety_check_passed": record.get("safety_check_passed"),
        "stage": record.get("stage"),
        "outcome": result.get("recovery_outcome") or {
            LiveDemoStage.HELD.value: Outcome.HELD_NO_ACTION.value,
            LiveDemoStage.ESCALATED.value: Outcome.PENDING_CUSTOMER_ACTION.value,
        }.get(record.get("stage")),
        "attempts": record.get("recovery_attempts", 0),
        "amount_recovered": result.get("amount_recovered", 0),
        "outcome_is_simulated": False,
        "failure_is_synthetic": False,
        "audit_trail": audit_trail,
    })


def _batch_showcase(results: list) -> dict:
    """A real record from the last batch run: synthetic failure, simulated
    outcome, labelled as such. Prefers one where the agent escalated, as it
    shows the most of the workflow."""
    r = next((r for r in results if any(e.step == "replan" for e in r.audit_trail)), results[0])
    audit_trail = [e.model_dump(mode="json") for e in r.audit_trail]
    return {
        "kind": "batch_record",
        "recorded_at": audit_trail[-1]["timestamp"] if audit_trail else None,
        "order_id": r.razorpay_order_id or r.order_id,
        "payment_id": r.payment_id,
        "razorpay_source": r.razorpay_source.value,
        "amount": r.amount,
        "failure_reason": r.failure_reason.value,
        "raw_error_code": r.raw_error_code,
        "action": r.action_taken.value,
        "safety_check_passed": not any(e.step == "safety_check" and "BLOCKED" in e.detail for e in r.audit_trail),
        "outcome": r.outcome.value,
        "attempts": r.attempt_count,
        "amount_recovered": r.amount_recovered,
        "outcome_is_simulated": True,
        "failure_is_synthetic": True,
        "audit_trail": audit_trail,
    }


@app.get("/api/showcase/case")
def showcase_case():
    """One real recorded case for the landing page: the latest live-demo
    result if there is one, otherwise a labelled batch record, otherwise
    kind="none" (the page shows an empty state)."""
    live = storage.get_value(SHOWCASE_LIVE_KEY)
    if live:
        return live
    results = _load_last_results()
    if results:
        return _batch_showcase(results)
    return {"kind": "none"}


def _agent_state(failure_reason: FailureReason, attempt_count: int, payment_id: str, audit_trail: list) -> AgentState:
    """Minimal agent state for running single nodes (select_recovery_action,
    safety_check) on a live-demo payment instead of a batch PaymentRecord."""
    class _Stub:
        pass
    stub_payment = _Stub()
    stub_payment.failure_reason = failure_reason
    stub_payment.attempt_count = attempt_count
    stub_payment.payment_id = payment_id
    return {
        "payment": stub_payment, "audit_trail": audit_trail,
        "action": None, "outcome": None, "amount_recovered": 0,
        "reasoning": "", "done": False,
    }


def _transition(order_id: str, allowed: set, update) -> dict:
    """Move a live-demo session forward atomically.

    Re-checks the stage inside the storage lock, so two requests can't
    both pass the same check (replays, double submits). `update(record)`
    returns the fields to change; the merged record is stored and returned."""
    def apply(current):
        record = _require_stage(current, order_id, allowed)
        return {**record, **update(record)}
    return storage.update_atomic(LIVE_DEMO_KEY_PREFIX + order_id, apply, ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)


class CreateDemoOrderRequest(BaseModel):
    # Paise. Bounded to a sane range for a demo order — ₹1 to ₹1,000 —
    # so the browser can't request an arbitrarily large or zero/negative
    # real Razorpay order.
    amount: int = Field(default=1000, ge=100, le=100_000)
    # Free-text tag for internal/display purposes only. Bounded length
    # and character set — this is never sent to Razorpay as the
    # receipt (see create_demo_order below), so it can't be used to
    # inject arbitrary content into a real API call.
    label: str = Field(default="live_demo", min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")


@app.get("/api/live-demo/config")
def live_demo_config():
    """Frontend needs the public Key ID (safe to expose client-side —
    this is Razorpay's standard Checkout pattern) to open Checkout."""
    return {
        "key_id": RAZORPAY_KEY_ID,
        # Live keys count as not configured: the demo only runs in test mode.
        "configured": bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET) and razorpay_key_mode() == "test",
    }


@app.post("/api/live-demo/create-order", dependencies=[limit_orders])
def create_demo_order(req: CreateDemoOrderRequest, token: str = Depends(access.require_session)):
    """
    REAL Razorpay Orders API call. The frontend takes the returned
    order_id and opens actual Razorpay Checkout against it.

    The receipt is generated server-side — the browser has no way to
    influence what gets sent to Razorpay as the receipt value.
    """
    access.require_orders(token)
    receipt = f"live_demo_{uuid.uuid4().hex[:16]}"
    try:
        order = create_real_order(amount=req.amount, receipt=receipt)
    except Exception as e:
        access.refund_orders(token, 1)
        raise _razorpay_error("create a real Razorpay order", e)
    _set_demo_record(order["id"], {"amount": req.amount, "stage": LiveDemoStage.ORDER_CREATED.value,
                                   "owner": access.owner_of(token)})
    return order


# ---- Live demo: failure -> decision -> execution -> customer -> verification (P7) ----
#
# A session is one live-demo order (key live_demo:<order_id>). After a real
# failure the agent decides and the executor acts at once: it opens a
# recovery request for the customer (now, after a delay, or with the failed
# method hidden), posts the message the customer would get to the demo
# outbox, or opens a support case. The customer pays on /recover/<token>
# (a page that needs only the token); the result is verified with Razorpay,
# from Checkout's report or a signed webhook, whichever arrives first. All
# of a session's state, its requests included, lives in its one record, so
# every change is one atomic update.

RECOVERY_TOKEN_PATTERN = r"^rr_[A-Za-z0-9_-]{20,64}$"
RECOVERY_TOKEN_PREFIX = "recovery_token:"     # token -> {"order_id": session order}
RECOVERY_ORDER_PREFIX = "recovery_order:"     # Razorpay recovery order id -> {"token": ...}
FINAL_STAGES = {LiveDemoStage.RECOVERED.value, LiveDemoStage.ESCALATED.value, LiveDemoStage.HELD.value}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _audit(payment_id: str, step: str, detail: str, data: Optional[dict] = None) -> dict:
    return AuditLogEntry(payment_id=payment_id, step=step, detail=detail, data=data).model_dump(mode="json")


def _short(token: str) -> str:
    """Tokens are the customer's access: never put a whole one in the audit trail."""
    return token[:9] + "…"


def _execute(record: dict, action: RecoveryAction, now: float) -> dict:
    """Carry out an approved action on a session record. Runs inside the
    storage lock; returns the fields to change."""
    attempt = record.get("recovery_attempts", 0) + 1
    plan = plan_execution(action, record["amount"], record.get("failed_method"))
    pid = record["original_payment_id"]
    trail = list(record.get("audit_trail", []))
    updates = {"recommended_action": action.value, "recovery_attempts": attempt, "current_request": None}

    if plan.kind == "support_case":
        case = {"id": f"case_{secrets.token_hex(5)}", "opened_at": _iso(now), "attempt": attempt,
                "failure_reason": record["failure_reason"],
                "note": "A support agent contacts the customer; the agent sends no payment request."}
        trail.append(_audit(pid, "execute", f"Attempt {attempt} of {MAX_ATTEMPTS}: {plan.summary} "
                                            f"Case {case['id']}.", data={"plan": plan.to_dict()}))
        updates.update(stage=LiveDemoStage.ESCALATED.value, support_case=case)
    else:
        token = "rr_" + secrets.token_urlsafe(24)
        link = f"/recover/{token}"
        request = {"token": token, "action": action.value, "attempt": attempt, "created_at": now,
                   "available_at": now + plan.delay_seconds,
                   "expires_at": now + plan.delay_seconds + RECOVERY_REQUEST_TTL_SECONDS,
                   "excluded_method": plan.excluded_method, "status": "open", "razorpay_order_id": None}
        message = {"at": _iso(now), "attempt": attempt, "action": action.value, "link": link,
                   "text": plan.customer_message.replace("{link}", link),
                   "channel": "SMS / email in production; shown in the demo outbox here"}
        trail.append(_audit(pid, "execute", f"Attempt {attempt} of {MAX_ATTEMPTS}: {plan.summary} "
                                            f"Request {_short(token)}.",
                            data={"plan": plan.to_dict()}))
        updates.update(stage=LiveDemoStage.AWAITING_CUSTOMER.value, current_request=token,
                       requests={**record.get("requests", {}), token: request},
                       outbox=list(record.get("outbox", [])) + [message])
    updates["audit_trail"] = trail
    return updates


def _after_failed_attempt(record: dict, now: float, why: str) -> dict:
    """A recovery request failed or went unpaid: re-plan to the next action
    and run it past the safety gate (which stops at MAX_ATTEMPTS)."""
    attempts = record.get("recovery_attempts", 0)
    current = RecoveryAction(record["recommended_action"])
    nxt = next_action(current)
    pid = record["original_payment_id"]
    trail = list(record.get("audit_trail", [])) + [
        _audit(pid, "replan", f"Attempt {attempts} failed ({why}). Escalating from "
                              f"'{current.value}' to '{nxt.value}'.")]
    gate = safety_check(_agent_state(FailureReason(record["failure_reason"]), attempts, pid, []))
    trail.append(gate["audit_trail"][-1].model_dump(mode="json"))
    if gate["done"]:
        return {"stage": LiveDemoStage.HELD.value, "current_request": None, "audit_trail": trail}
    return _execute({**record, "audit_trail": trail}, nxt, now)


def _store_tokens(record: dict, order_id: str) -> None:
    token = record.get("current_request")
    if token:
        storage.set_value(RECOVERY_TOKEN_PREFIX + token, {"order_id": order_id},
                          ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)


def _finish(order_id: str, record: dict) -> dict:
    """Side effects after a stored change: token index, showcase."""
    _store_tokens(record, order_id)
    if record.get("stage") in FINAL_STAGES:
        _record_showcase(order_id, record)
    return record


def _validate_failed_payment(payment: dict, order_id: str, record: dict) -> None:
    """Never trust a reported pairing: Razorpay's own payment record must
    belong to this order, match the amount and currency, and have failed."""
    payment_id = payment.get("id")
    if payment.get("order_id") != order_id:
        raise HTTPException(status_code=400, detail=f"Payment {payment_id} belongs to Razorpay order "
                                                    f"'{payment.get('order_id')}', not the claimed order_id '{order_id}'.")
    if payment.get("amount") != record.get("amount"):
        raise HTTPException(status_code=400, detail=f"Payment amount ({payment.get('amount')}) does not match the "
                                                    f"order's expected amount ({record.get('amount')}).")
    if payment.get("currency") != "INR":
        raise HTTPException(status_code=400, detail=f"Unexpected currency '{payment.get('currency')}' — expected INR.")
    status = payment.get("status")
    if status in ("created", "authorized"):
        raise HTTPException(status_code=409, detail=f"Payment {payment_id} is '{status}', not final yet. "
                                                    f"Report it once it has failed.")
    if status != "failed":
        raise HTTPException(status_code=400, detail=f"Payment {payment_id} is '{status}', not failed; "
                                                    f"only a failed payment starts a recovery.")


def _record_failure(order_id: str, payment: dict, source: str) -> dict:
    """Classify a real failed payment, decide, gate and execute. `source`
    is "checkout" (the browser reported it) or "webhook" (Razorpay did)."""
    failure_reason, raw_error_code = classify_real_payment_error(payment)
    payment_id = payment["id"]
    audit_trail = [AuditLogEntry(
        payment_id=payment_id, step="classify",
        detail=f"Fetched real payment {payment_id} from Razorpay ({source}). error_reason="
               f"'{payment.get('error_reason')}' mapped to '{failure_reason.value}' (method: {payment.get('method')}).")]
    state = _agent_state(failure_reason, attempt_count=0, payment_id=payment_id, audit_trail=audit_trail)
    state = select_recovery_action(state)
    state = safety_check(state)
    safety_passed = not state["done"]
    now = time.time()

    def update(record):
        base = {**record, "original_payment_id": payment_id, "failure_reason": failure_reason.value,
                "raw_error_code": raw_error_code, "failed_method": payment.get("method"),
                "recommended_action": state["action"].value, "safety_check_passed": safety_passed,
                "recovery_attempts": 0, "audit_trail": [e.model_dump(mode="json") for e in state["audit_trail"]]}
        if not safety_passed:
            return {**base, "stage": LiveDemoStage.HELD.value}
        return {**base, **_execute(base, state["action"], now)}

    stored = _transition(order_id, {LiveDemoStage.ORDER_CREATED}, update)
    return _finish(order_id, stored)


def _expire_if_due(order_id: str) -> Optional[dict]:
    """Lazily treat an unpaid, expired request as a failed attempt."""
    now = time.time()

    def apply(record):
        if not record or record.get("stage") != LiveDemoStage.AWAITING_CUSTOMER.value:
            raise _NothingToDo()
        token = record["current_request"]
        request = record["requests"][token]
        if request["expires_at"] > now:
            raise _NothingToDo()
        requests = {**record["requests"], token: {**request, "status": "expired"}}
        record = {**record, "requests": requests}
        return {**record, **_after_failed_attempt(record, now, "the customer didn't pay before the request expired")}

    try:
        stored = storage.update_atomic(LIVE_DEMO_KEY_PREFIX + order_id, apply, ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)
    except _NothingToDo:
        return None
    return _finish(order_id, stored)


class _NothingToDo(Exception):
    """Aborts an atomic update without writing."""


def _request_view(record: dict, token: str, now: float, include_link: bool) -> dict:
    request = record["requests"][token]
    status = request["status"]
    if status == "open" and record.get("current_request") != token:
        status = "superseded"
    wait = max(0, math.ceil(request["available_at"] - now))
    if status == "open" and wait > 0:
        status = "scheduled"
    view = {
        "status": status, "action": request["action"], "attempt": request["attempt"], "max_attempts": MAX_ATTEMPTS,
        "seconds_until_available": wait, "available_at": _iso(request["available_at"]),
        "expires_at": _iso(request["expires_at"]), "excluded_method": request["excluded_method"],
        "has_order": request["razorpay_order_id"] is not None,
    }
    if include_link:
        view["link"] = f"/recover/{token}"
    return view


def _operator_view(order_id: str, record: dict) -> dict:
    now = time.time()
    token = record.get("current_request")
    result = record.get("result")
    return {
        "order_id": order_id, "stage": record["stage"], "amount": record["amount"],
        "failure_reason": record.get("failure_reason"), "raw_error_code": record.get("raw_error_code"),
        "failed_method": record.get("failed_method"), "recommended_action": record.get("recommended_action"),
        "safety_check_passed": record.get("safety_check_passed"),
        "recovery_attempts": record.get("recovery_attempts", 0), "max_attempts": MAX_ATTEMPTS,
        "current_request": _request_view(record, token, now, include_link=True) if token else None,
        "outbox": record.get("outbox", []), "support_case": record.get("support_case"),
        "result": result, "audit_trail": record.get("audit_trail", []),
    }


@app.post("/api/live-demo/report-failure", dependencies=[limit_reports])
def report_failure(order_id: str = Query(..., pattern=ORDER_ID_PATTERN),
                   payment_id: str = Query(..., pattern=PAYMENT_ID_PATTERN),
                   token: str = Depends(access.require_session)):
    """The browser reports a failed Checkout payment. The server fetches the
    real payment from Razorpay, then the agent classifies, decides, gates and
    executes. (A signed payment.failed webhook does the same without the browser.)"""
    # Fast check before calling Razorpay; re-checked atomically when written.
    order_record = _require_stage(_get_demo_record(order_id), order_id, {LiveDemoStage.ORDER_CREATED})
    _require_owner(order_record, token, order_id)
    try:
        payment = fetch_real_payment(payment_id)
    except Exception as e:
        raise _razorpay_error("fetch the real payment from Razorpay", e)
    _validate_failed_payment(payment, order_id, order_record)
    return _operator_view(order_id, _record_failure(order_id, payment, "checkout"))


@app.get("/api/live-demo/session", dependencies=[limit_reports])
def live_demo_session(order_id: str = Query(..., pattern=ORDER_ID_PATTERN),
                      token: str = Depends(access.require_session)):
    """The operator's view of a session: stage, what the agent executed,
    the outbox, the support case and the verified result. Polled while the
    customer has the recovery request."""
    record = _get_demo_record(order_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Unknown order_id '{order_id}'.")
    _require_owner(record, token, order_id)
    record = _expire_if_due(order_id) or record
    return _operator_view(order_id, record)


# ---- The customer's side: /recover/<token> ----

def _load_request(token: str) -> tuple[str, dict]:
    index = storage.get_value(RECOVERY_TOKEN_PREFIX + token)
    record = _get_demo_record(index["order_id"]) if index else None
    if not record or token not in record.get("requests", {}):
        raise HTTPException(status_code=404, detail="This recovery link doesn't exist or has expired.")
    return index["order_id"], record


def _checkout_config(excluded_method: Optional[str]) -> Optional[dict]:
    """Razorpay Checkout display config that hides the failed method."""
    if not excluded_method:
        return None
    return {"display": {"hide": [{"method": excluded_method}], "preferences": {"show_default_blocks": True}}}


def _customer_view(record: dict, token: str) -> dict:
    now = time.time()
    request = record["requests"][token]
    view = _request_view(record, token, now, include_link=False)
    if record.get("stage") == LiveDemoStage.ESCALATED.value and view["status"] in ("superseded", "failed"):
        view["status"] = "escalated"
    return {
        **view, "merchant": MERCHANT_NAME, "amount": record["amount"], "currency": "INR",
        "failure_reason": record.get("failure_reason"), "key_id": RAZORPAY_KEY_ID,
        "order": ({"id": request["razorpay_order_id"], "amount": record["amount"], "currency": "INR"}
                  if request["razorpay_order_id"] and view["status"] == "open" else None),
        "checkout_config": _checkout_config(request["excluded_method"]),
        "amount_recovered": (record.get("result") or {}).get("amount_recovered", 0) if view["status"] == "paid" else 0,
    }


@app.get("/api/recover/{token}", dependencies=[limit_reports])
def recovery_request(token: str = Path(..., pattern=RECOVERY_TOKEN_PATTERN)):
    """What the customer sees. The token is their only access."""
    order_id, _ = _load_request(token)
    _expire_if_due(order_id)
    _, record = _load_request(token)
    return _customer_view(record, token)


@app.post("/api/recover/{token}/order", dependencies=[limit_orders])
def recovery_order(token: str = Path(..., pattern=RECOVERY_TOKEN_PATTERN)):
    """Create (once) the real Razorpay order the customer pays this request
    with. Counts against the demo session's order budget and the daily cap."""
    order_id, record = _load_request(token)
    _expire_if_due(order_id)
    order_id, record = _load_request(token)
    view = _customer_view(record, token)
    if view["status"] == "scheduled":
        raise HTTPException(status_code=409, detail=f"Not yet: this payment opens in {view['seconds_until_available']} s.")
    if view["status"] != "open":
        raise HTTPException(status_code=409, detail="This recovery link is no longer active.")
    request = record["requests"][token]
    if request["razorpay_order_id"]:
        return {"order": view["order"], "checkout_config": view["checkout_config"]}

    owner = record["owner"]
    try:
        access.require_orders_for_owner(owner)
    except HTTPException as e:
        if e.status_code == 401:
            raise HTTPException(status_code=410, detail="This recovery link has expired.")
        raise
    try:
        order = create_real_order(amount=record["amount"], receipt=f"recovery_{secrets.token_hex(8)}")
    except Exception as e:
        access.refund_orders_for_owner(owner, 1)
        raise _razorpay_error("create the recovery order", e)

    created = {"won": False}

    def bind(current):
        current = _require_stage(current, order_id, {LiveDemoStage.AWAITING_CUSTOMER})
        req = current["requests"][token]
        if current.get("current_request") != token or req["razorpay_order_id"]:
            raise _NothingToDo()
        created["won"] = True
        return {**current, "requests": {**current["requests"], token: {**req, "razorpay_order_id": order["id"]}}}

    try:
        record = storage.update_atomic(LIVE_DEMO_KEY_PREFIX + order_id, bind, ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)
    except _NothingToDo:
        access.refund_orders_for_owner(owner, 1)    # lost a race: another request bound its order first
        record = _get_demo_record(order_id)
    if created["won"]:
        storage.set_value(RECOVERY_ORDER_PREFIX + order["id"], {"token": token}, ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)
    view = _customer_view(record, token)
    if not view["order"]:
        raise HTTPException(status_code=409, detail="This recovery link is no longer active.")
    return {"order": view["order"], "checkout_config": view["checkout_config"]}


def _settle(token: str, payment: dict, source: str, signature_ok: bool = False) -> dict:
    """Record the outcome of the customer's payment on a recovery request.
    `source` is "checkout" (needs Checkout's signature for a capture) or
    "webhook" (already verified by the webhook signature)."""
    order_id, record = _load_request(token)
    request = record["requests"][token]
    payment_id = payment.get("id")
    if not request["razorpay_order_id"] or payment.get("order_id") != request["razorpay_order_id"]:
        raise HTTPException(status_code=400, detail=f"Payment {payment_id} belongs to Razorpay order "
                                                    f"'{payment.get('order_id')}', not this recovery request's order.")
    if payment.get("amount") != record.get("amount"):
        raise HTTPException(status_code=400, detail=f"Recovery payment amount ({payment.get('amount')}) does not "
                                                    f"match the original amount ({record.get('amount')}).")
    if payment.get("currency") != "INR":
        raise HTTPException(status_code=400, detail=f"Unexpected currency '{payment.get('currency')}' — expected INR.")
    status = payment.get("status")
    if status not in ("captured", "failed"):
        raise HTTPException(status_code=409, detail=f"Recovery payment {payment_id} is '{status}', not final yet. "
                                                    f"Try again shortly.")
    recovered = status == "captured"
    if recovered and source == "checkout" and not signature_ok:
        raise HTTPException(status_code=400, detail="Missing or invalid razorpay_signature for this recovery "
                                                    "payment; a recovery is only recorded with Checkout's signed "
                                                    "success response.")
    now = time.time()

    def apply(current):
        current = _require_stage(current, order_id, {LiveDemoStage.AWAITING_CUSTOMER})
        req = current["requests"].get(token)
        # Re-checked under the lock: still this request, still its order, not settled.
        if current.get("current_request") != token or not req or req["razorpay_order_id"] != payment.get("order_id") \
                or req["status"] != "open":
            raise HTTPException(status_code=409, detail="This recovery request has already been settled or replaced.")
        requests = {**current["requests"], token: {**req, "status": "paid" if recovered else "failed",
                                                   "payment_id": payment_id}}
        trail = list(current.get("audit_trail", [])) + [_audit(
            payment_id, "execute",
            f"Customer paid recovery request {_short(token)} on order {req['razorpay_order_id']}: Razorpay "
            f"status '{status}' ({'Checkout report + signature' if source == 'checkout' else 'signed webhook'}).")]
        current = {**current, "requests": requests, "audit_trail": trail}
        if not recovered:
            return {**current, **_after_failed_attempt(current, now, "the customer's payment failed")}
        result = LiveDemoResult(
            original_order_id=order_id, original_payment_id=current["original_payment_id"],
            recovery_order_id=req["razorpay_order_id"], recovery_payment_id=payment_id,
            amount=current["amount"], failure_reason=current["failure_reason"],
            raw_error_code=current["raw_error_code"], recommended_action=current["recommended_action"],
            safety_check_passed=current["safety_check_passed"], recovery_outcome=Outcome.RECOVERED,
            outcome_is_simulated=False, amount_recovered=payment.get("amount", 0), audit_trail=trail)
        return {**current, "stage": LiveDemoStage.RECOVERED.value, "current_request": None,
                "result": result.model_dump(mode="json")}

    stored = storage.update_atomic(LIVE_DEMO_KEY_PREFIX + order_id, apply, ttl_seconds=storage.LIVE_DEMO_TTL_SECONDS)
    return _finish(order_id, stored)


@app.post("/api/recover/{token}/report", dependencies=[limit_reports])
def recovery_report(token: str = Path(..., pattern=RECOVERY_TOKEN_PATTERN),
                    payment_id: str = Query(..., pattern=PAYMENT_ID_PATTERN),
                    razorpay_signature: Optional[str] = Query(None, max_length=128)):
    """The customer's Checkout finished. The server fetches the payment from
    Razorpay; a capture also needs Checkout's signature for this order."""
    order_id, record = _load_request(token)
    request = record["requests"][token]
    if not request["razorpay_order_id"]:
        raise HTTPException(status_code=409, detail="No payment has been started on this recovery link.")
    try:
        payment = fetch_real_payment(payment_id)
    except Exception as e:
        raise _razorpay_error("fetch the recovery payment from Razorpay", e)
    signature_ok = verify_checkout_signature(request["razorpay_order_id"], payment_id, razorpay_signature)
    record = _settle(token, payment, "checkout", signature_ok)
    return _customer_view(record, token)


# ---- Razorpay webhooks ----

WEBHOOK_EVENT_PREFIX = "webhook_event:"


def _handle_webhook_event(event: dict) -> str:
    name = event.get("event")
    payment = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_id = payment.get("order_id")
    if name not in ("payment.failed", "payment.captured", "order.paid") or not order_id:
        return "ignored"
    rr = storage.get_value(RECOVERY_ORDER_PREFIX + order_id)
    try:
        if rr:                                                 # a payment on a recovery request
            _settle(rr["token"], payment, "webhook")
            return "recovery_settled"
        record = _get_demo_record(order_id)
        if name == "payment.failed" and record and record.get("stage") == LiveDemoStage.ORDER_CREATED.value:
            _validate_failed_payment(payment, order_id, record)
            _record_failure(order_id, payment, "webhook")
            return "failure_recorded"
    except HTTPException as e:
        if e.status_code == 409:
            return "already_recorded"       # Checkout's report got there first
        raise
    return "ignored"


@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    """Razorpay's server-to-server events, verified with X-Razorpay-Signature
    over the raw body. De-duplicated by event id (Razorpay retries)."""
    if not razorpay_webhook_configured():
        raise HTTPException(status_code=503, detail="Webhooks aren't configured on this server.")
    raw = await request.body()
    if not verify_webhook_signature(raw, request.headers.get("x-razorpay-signature")):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Webhook body is not JSON.")

    event_id = request.headers.get("x-razorpay-event-id")
    if event_id:
        def claim(current):
            if current:
                raise _NothingToDo()
            return {"received_at": time.time()}
        try:
            await run_in_threadpool(storage.update_atomic, WEBHOOK_EVENT_PREFIX + event_id, claim, 2 * 86400)
        except _NothingToDo:
            return {"status": "duplicate"}
    try:
        status = await run_in_threadpool(_handle_webhook_event, event)
    except HTTPException as e:
        # A mismatched payment is logged and acknowledged; Razorpay retrying won't fix it.
        logger.warning("Webhook event %s rejected: %s", event.get("event"), e.detail)
        status = "rejected"
    return {"status": status}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
