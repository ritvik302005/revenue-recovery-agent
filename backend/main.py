"""
FastAPI application for the AI Revenue Recovery agent.

Endpoints:
  POST /api/batch/run       - generate a batch and run the recovery agent on it
  GET  /api/batch/results   - fetch the last run's results
  GET  /api/batch/metrics   - summary metrics, split real vs simulated
  GET  /api/health          - basic health check + Razorpay connectivity status
"""
from fastapi import FastAPI, Query, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import json
import os
import time
from collections import defaultdict

from models import RazorpaySource, Outcome, LiveDemoResult, AuditLogEntry, RecoveryResult, LiveDemoStage, FailureReason
from simulate_batch import generate_batch
from recovery_agent import run_recovery, select_recovery_action, safety_check, AgentState, MAX_ATTEMPTS
from razorpay_client import (
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    create_real_order, fetch_real_payment, classify_real_payment_error,
    verify_checkout_signature,
)
from pydantic import BaseModel, Field, ValidationError
import logging
import uuid
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
    allow_headers=["Content-Type", "X-API-Key"],
)

# ---- API-key authorization ----
# Set API_KEY in the environment to require it on state-changing
# endpoints (order creation, batch runs, live-demo reporting). If unset
# (e.g. local dev), these endpoints stay open — same as before.
API_KEY = os.environ.get("API_KEY")


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")


# ---- Rate limiting ----
# Simple in-memory sliding-window limiter, per client IP, for the
# order-creation endpoints (each call hits Razorpay's real API). Good
# enough for a single-process deployment; swap for a shared store
# (e.g. Redis) if this ever runs behind multiple workers/instances.
_rate_limit_buckets: dict[str, list] = defaultdict(list)
RATE_LIMIT_MAX_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60


def rate_limit(request: Request):
    now = time.time()
    client_ip = request.client.host if request.client else "unknown"
    bucket = _rate_limit_buckets[client_ip]
    while bucket and bucket[0] < now - RATE_LIMIT_WINDOW_SECONDS:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests — please slow down and try again shortly.")
    bucket.append(now)

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
    keys_present = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)
    return {
        "status": "ok",
        "razorpay_keys_configured": keys_present,
        "razorpay_live_connectivity": "unverified",  # flip only after verify_razorpay_connection.py succeeds
    }


@app.post("/api/batch/run", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def run_batch(n: int = Query(60, ge=1, le=500), try_live_orders: bool = Query(False),
              seed: int = Query(DEFAULT_BATCH_SEED, ge=0, le=2**31 - 1)):
    """Same seed -> same synthetic batch and same simulated outcomes.
    try_live_orders (off by default) creates real test orders for at most
    MAX_LIVE_ORDERS_PER_BATCH records and stops at the first failure."""
    batch = generate_batch(n=n, seed=seed, try_live_orders=try_live_orders)
    results = [run_recovery(p) for p in batch]
    _save_last_results(results, seed)
    return {"count": len(results), "seed": seed, "results": [r.model_dump() for r in results]}


@app.get("/api/batch/results")
def get_results():
    results = _load_last_results()
    return {"count": len(results), "seed": _last_batch_seed() if results else None,
            "results": [r.model_dump() for r in results]}


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
        "outcome": result.get("recovery_outcome") or (Outcome.HELD_NO_ACTION.value
                                                      if record.get("stage") == LiveDemoStage.HELD.value else None),
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
        "configured": bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET),
    }


@app.post("/api/live-demo/create-order", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def create_demo_order(req: CreateDemoOrderRequest):
    """
    REAL Razorpay Orders API call. The frontend takes the returned
    order_id and opens actual Razorpay Checkout against it.

    The receipt is generated server-side — the browser has no way to
    influence what gets sent to Razorpay as the receipt value.
    """
    receipt = f"live_demo_{uuid.uuid4().hex[:16]}"
    try:
        order = create_real_order(amount=req.amount, receipt=receipt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not create a real Razorpay order: {e}")
    _set_demo_record(order["id"], {"amount": req.amount, "stage": LiveDemoStage.ORDER_CREATED.value})
    return order


@app.post("/api/live-demo/report-failure", dependencies=[Depends(require_api_key)])
def report_failure(order_id: str = Query(..., pattern=ORDER_ID_PATTERN),
                   payment_id: str = Query(..., pattern=PAYMENT_ID_PATTERN)):
    """
    Called after the user completes Checkout with a FAILING test
    instrument. Fetches the REAL payment object from Razorpay, maps
    its real error_reason to our taxonomy, then runs the agent's
    classify -> select_action -> safety_check nodes (not execute —
    the actual recovery attempt happens via a second real Checkout,
    see /report-recovery).
    """
    # Fast check before calling Razorpay; re-checked atomically when the
    # stage is written below, so a replay can't slip in between.
    order_record = _require_stage(_get_demo_record(order_id), order_id, {LiveDemoStage.ORDER_CREATED})

    try:
        payment = fetch_real_payment(payment_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch real payment from Razorpay: {e}")

    # Ownership/amount/currency checks — never trust the caller's
    # order_id/payment_id pairing without verifying Razorpay's own
    # payment record actually belongs to that order and amount.
    if payment.get("order_id") != order_id:
        raise HTTPException(
            status_code=400,
            detail=f"Payment {payment_id} belongs to Razorpay order "
                   f"'{payment.get('order_id')}', not the claimed order_id '{order_id}'.",
        )
    if payment.get("amount") != order_record.get("amount"):
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount ({payment.get('amount')}) does not match the "
                   f"order's expected amount ({order_record.get('amount')}).",
        )
    if payment.get("currency") != "INR":
        raise HTTPException(status_code=400, detail=f"Unexpected currency '{payment.get('currency')}' — expected INR.")

    # Only a payment Razorpay itself reports as failed starts a recovery.
    status = payment.get("status")
    if status in ("created", "authorized"):
        raise HTTPException(
            status_code=409,
            detail=f"Payment {payment_id} is '{status}', not final yet. Report it once it has failed.",
        )
    if status != "failed":
        raise HTTPException(
            status_code=400,
            detail=f"Payment {payment_id} is '{status}', not failed; only a failed payment starts a recovery.",
        )

    failure_reason, raw_error_code = classify_real_payment_error(payment)

    audit_trail = [
        AuditLogEntry(payment_id=payment_id, step="classify",
                      detail=f"Fetched real payment {payment_id} from Razorpay. "
                             f"error_reason='{payment.get('error_reason')}' mapped to "
                             f"'{failure_reason.value}'.")
    ]

    # Reuse the same select_recovery_action / safety_check nodes the
    # batch agent uses, on a minimal state.
    state = _agent_state(failure_reason, attempt_count=0, payment_id=payment_id, audit_trail=audit_trail)
    state = select_recovery_action(state)
    state = safety_check(state)

    safety_passed = not state["done"]
    stored = _transition(order_id, {LiveDemoStage.ORDER_CREATED}, lambda record: {
        "original_payment_id": payment_id,
        "failure_reason": failure_reason,
        "raw_error_code": raw_error_code,
        "recommended_action": state["action"],
        "safety_check_passed": safety_passed,
        "stage": (LiveDemoStage.FAILURE_RECORDED if safety_passed else LiveDemoStage.HELD).value,
        "audit_trail": [e.model_dump(mode="json") for e in state["audit_trail"]],
    })
    if not safety_passed:
        _record_showcase(order_id, stored)   # held by the safety gate: a finished case

    return {
        "failure_reason": failure_reason.value,
        "raw_error_code": raw_error_code,
        "recommended_action": state["action"].value,
        "safety_check_passed": safety_passed,
        "stage": (LiveDemoStage.FAILURE_RECORDED if safety_passed else LiveDemoStage.HELD).value,
        "audit_trail": [a.model_dump() for a in state["audit_trail"]],
    }


@app.post("/api/live-demo/create-recovery-order", dependencies=[Depends(require_api_key), Depends(rate_limit)])
def create_recovery_order(order_id: str = Query(..., pattern=ORDER_ID_PATTERN)):
    """
    Creates the recovery order for a recorded failure — server-side, for
    the original amount — and binds it to the session. report-recovery
    only accepts a payment on exactly this order, so the browser can't
    pick an unrelated (or the original) order as the "recovery".
    """
    retryable = {LiveDemoStage.FAILURE_RECORDED, LiveDemoStage.RECOVERY_FAILED}
    record = _require_stage(_get_demo_record(order_id), order_id, retryable)

    # The same hard safety gate the batch agent uses, with the recovery
    # attempts made so far: once MAX_ATTEMPTS are used, no new order.
    attempts = record.get("recovery_attempts", 0)
    gate = safety_check(_agent_state(FailureReason(record["failure_reason"]), attempts,
                                     record["original_payment_id"], []))
    if gate["done"]:
        blocked = gate["audit_trail"][-1].model_dump(mode="json")
        stored = _transition(order_id, retryable, lambda record: {
            "stage": LiveDemoStage.HELD.value,
            "audit_trail": record.get("audit_trail", []) + [blocked],
        })
        _record_showcase(order_id, stored)
        raise HTTPException(
            status_code=409,
            detail=f"Safety gate blocked another recovery attempt: {attempts} of {MAX_ATTEMPTS} attempts used.",
        )

    receipt = f"live_recovery_{uuid.uuid4().hex[:16]}"
    try:
        order = create_real_order(amount=record["amount"], receipt=receipt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not create a real Razorpay recovery order: {e}")

    _transition(order_id, retryable, lambda record: {
        "stage": LiveDemoStage.RECOVERY_ORDER_CREATED.value,
        "current_recovery_order_id": order["id"],
        "audit_trail": record.get("audit_trail", []) + [
            AuditLogEntry(payment_id=record["original_payment_id"], step="execute",
                          detail=f"Recovery attempt {attempts + 1} of {MAX_ATTEMPTS}: created order "
                                 f"{order['id']} for the original amount ({record['amount']} paise)."
                          ).model_dump(mode="json")
        ],
    })
    return order


@app.post("/api/live-demo/report-recovery", dependencies=[Depends(require_api_key)])
def report_recovery(order_id: str = Query(..., pattern=ORDER_ID_PATTERN),
                    recovery_payment_id: str = Query(..., pattern=PAYMENT_ID_PATTERN),
                    recovery_order_id: str = Query(..., pattern=ORDER_ID_PATTERN),
                    razorpay_signature: Optional[str] = Query(None, max_length=128)):
    """
    Called after the user completes the recovery Checkout on the order
    from /create-recovery-order. Fetches the real payment status — this
    is a genuinely real outcome, not simulated.

    A captured payment also needs the razorpay_signature Checkout returned
    on success. A failed attempt has no signature (Razorpay's
    payment.failed event doesn't carry one) and is recorded from the
    fetched status alone.
    """
    record = _require_stage(_get_demo_record(order_id), order_id, {LiveDemoStage.RECOVERY_ORDER_CREATED})
    if recovery_order_id != record.get("current_recovery_order_id") or recovery_order_id == order_id:
        raise HTTPException(
            status_code=400,
            detail=f"'{recovery_order_id}' is not the recovery order created for order '{order_id}'. "
                   f"Use the order returned by /create-recovery-order.",
        )

    try:
        payment = fetch_real_payment(recovery_payment_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch real recovery payment from Razorpay: {e}")

    # Ownership/amount/currency checks — a captured payment only
    # counts as a recovery if it's genuinely the recovery order's own
    # payment, for the same amount and currency as the original.
    if payment.get("order_id") != recovery_order_id:
        raise HTTPException(
            status_code=400,
            detail=f"Payment {recovery_payment_id} belongs to Razorpay order "
                   f"'{payment.get('order_id')}', not the claimed recovery_order_id "
                   f"'{recovery_order_id}'.",
        )
    if payment.get("amount") != record.get("amount"):
        raise HTTPException(
            status_code=400,
            detail=f"Recovery payment amount ({payment.get('amount')}) does not match "
                   f"the original amount ({record.get('amount')}).",
        )
    if payment.get("currency") != "INR":
        raise HTTPException(status_code=400, detail=f"Unexpected currency '{payment.get('currency')}' — expected INR.")

    real_status = payment.get("status")  # "captured" = success in Razorpay test mode
    if real_status not in ("captured", "failed"):
        # e.g. "created"/"authorized": not final yet. Don't record an
        # outcome (or use up the attempt) on a payment still in flight.
        raise HTTPException(
            status_code=409,
            detail=f"Recovery payment {recovery_payment_id} is '{real_status}', not final yet. Try again shortly.",
        )
    recovered = real_status == "captured"
    if recovered and not verify_checkout_signature(recovery_order_id, recovery_payment_id, razorpay_signature):
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid razorpay_signature for this recovery payment; "
                   "a recovery is only recorded with Checkout's signed success response.",
        )

    outcome = Outcome.RECOVERED if recovered else Outcome.STILL_FAILED
    amount_recovered = payment.get("amount", 0) if recovered else 0

    def record_outcome(record: dict) -> dict:
        # Re-checked under the storage lock: still the same recovery order.
        if record.get("current_recovery_order_id") != recovery_order_id:
            raise HTTPException(status_code=409, detail="The recovery order for this session changed; reload and retry.")
        audit_trail = list(record.get("audit_trail", [])) + [
            AuditLogEntry(
                payment_id=recovery_payment_id, step="execute",
                detail=f"Real recovery Checkout attempt completed on order {recovery_order_id}. "
                       f"Razorpay payment status='{real_status}'. Outcome: {outcome.value}.",
            ).model_dump(mode="json")
        ]
        result = LiveDemoResult(
            original_order_id=order_id,
            original_payment_id=record["original_payment_id"],
            recovery_order_id=recovery_order_id,
            recovery_payment_id=recovery_payment_id,
            amount=record["amount"],
            failure_reason=record["failure_reason"],
            raw_error_code=record["raw_error_code"],
            recommended_action=record["recommended_action"],
            safety_check_passed=record["safety_check_passed"],
            recovery_outcome=outcome,
            outcome_is_simulated=False,
            amount_recovered=amount_recovered,
            audit_trail=audit_trail,
        )
        return {
            "stage": (LiveDemoStage.RECOVERED if recovered else LiveDemoStage.RECOVERY_FAILED).value,
            "recovery_attempts": record.get("recovery_attempts", 0) + 1,
            "audit_trail": audit_trail,
            "result": result.model_dump(mode="json"),
        }

    stored = _transition(order_id, {LiveDemoStage.RECOVERY_ORDER_CREATED}, record_outcome)
    _record_showcase(order_id, stored)
    return {**stored["result"], "stage": stored["stage"],
            "recovery_attempts": stored["recovery_attempts"], "max_attempts": MAX_ATTEMPTS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
