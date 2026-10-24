# ARCHITECTURE.md

How the system is built **today** (verified by the audit of 2026-10-24) and the **target** after Phases 1–5. Update the "Current" sections as tasks land; when a target item is done, move it up.

> The root-level `ARCHITECTURE.md` and `EVALUATION_REPORT.md` are older and partly wrong (in-memory storage, CORS `*`, live demo "not wired", max-attempts diagram). Trust this file. Task P3-7 rewrites the root docs.

---

## 1. Overview

```
Browser (React + Vite)
   │  fetch, JSON                        Razorpay Checkout (popup, checkout.js)
   ▼                                              │ payment.failed / handler
FastAPI  backend/main.py  ◄──────────────────────┘ (payment_id reported by the browser)
   │
   ├── recovery_agent.py   LangGraph graph (rule-based)
   ├── simulate_batch.py   synthetic batch generator
   ├── razorpay_client.py  Razorpay SDK: create order, fetch payment (8 s timeout)
   └── storage.py          key/value store: Redis if REDIS_URL, else SQLite state.db
```

Stack: Python (FastAPI 0.141, LangGraph 1.2, Pydantic 2, razorpay SDK 2.0) · React 18, Vite 5 · no CSS framework (one large `index.css`).

## 2. Backend files

| File | Role |
|---|---|
| `main.py` | All endpoints, CORS, optional API key, in-memory rate limiter, live-demo session logic |
| `recovery_agent.py` | Agent graph, action table, safety gate, simulated outcome model |
| `simulate_batch.py` | Seeded synthetic batch; optionally creates real Razorpay orders per record |
| `razorpay_client.py` | SDK client with timeout adapter; `create_real_order`, `fetch_real_payment`, `classify_real_payment_error`; error taxonomy table |
| `models.py` | Enums (`FailureReason`, `RecoveryAction`, `Outcome`, `RazorpaySource`, `LiveDemoStage` – unused), Pydantic models |
| `storage.py` | `set_value` / `get_value` / `delete_value`, optional TTL |
| `verify_razorpay_connection.py` | Creates one real ₹10 test order to check keys |
| `tests/` | 30 tests: safety gate, metrics labelling, report-recovery validation |

## 3. Endpoints (current)

| Method | Path | Auth | Rate limit | Calls Razorpay | Notes |
|---|---|---|---|---|---|
| GET | `/api/health` | – | – | no | `razorpay_live_connectivity` is a fixed `"unverified"` |
| POST | `/api/batch/run?n&try_live_orders` | API key if set | 10/min/IP | yes, up to n orders | n ≤ 500; synchronous |
| GET | `/api/batch/results` | – | – | no | Last batch from storage |
| GET | `/api/batch/metrics` | – | – | no | 404 before first batch |
| GET | `/api/live-demo/config` | – | – | no | Returns public `key_id` |
| POST | `/api/live-demo/create-order` | API key if set | 10/min/IP | yes | ₹1–₹1,000, receipt generated server-side |
| POST | `/api/live-demo/report-failure?order_id&payment_id` | API key if set | **none** | yes | Stage `order_created` → `failure_recorded` / `held`; checks order/amount/INR; **no status check yet (P2-1)** |
| POST | `/api/live-demo/create-recovery-order?order_id` | API key if set | 10/min/IP | yes | Stage `failure_recorded` → `recovery_order_created`; server creates the order for the original amount and stores `current_recovery_order_id` |
| POST | `/api/live-demo/report-recovery?order_id&recovery_order_id&recovery_payment_id` | API key if set | **none** | yes | Stage `recovery_order_created` → `recovered` / `recovery_failed`; `recovery_order_id` must equal the stored one; non-final payment status → 409 without recording |

Out-of-order or repeated calls return **409**; unknown sessions **404**. Every stage change is an atomic read-check-write (`storage.update_atomic`).

## 4. Agent (current)

Graph: `classify → select_action → safety_check → execute → (should_replan) → escalate → safety_check …`

- **classify**: logs the failure reason already on the record. Computes nothing.
- **select_action**: fixed table, failure reason → action.
- **safety_check**: fraud → `NO_ACTION_FRAUD_HOLD` / `HELD_NO_ACTION`, stop. `attempt_count ≥ 3` → `NO_ACTION_MAX_ATTEMPTS` / `STILL_FAILED`, stop.
- **execute**: `attempt_count += 1`; success if `random.Random(f"{payment_id}-{attempt}") < RECOVERY_PROBABILITY[(reason, action)]` (default 0.25). Reminder link / support failing → `PENDING_CUSTOMER_ACTION`. Done when recovered or attempt ≥ 3.
- **should_replan**: replan only if `STILL_FAILED` and attempts < 3.
- **escalate**: retry_same → alternate method → reminder link → support; retry_with_delay → alternate method.

Measured behaviour (200 runs × 60): recovery rate 50–88% (mean 66%); outcomes only `recovered` or `pending`; `still_failed` and the max-attempts gate never occur; seed-42 batch of 60 has no fraud case.

## 5. Live demo flow

### Current (after P1-1, P1-2)
```
create-order (amount) ──► stage=order_created ──► Checkout (failing test card) ──► payment.failed
   ──► report-failure(order_id, payment_id) ──► stage=failure_recorded   (or held if the safety gate blocks)
create-recovery-order(order_id) ──► server creates order, stores current_recovery_order_id
   ──► stage=recovery_order_created ──► Checkout (success test card) ──► handler / payment.failed
   ──► report-recovery(order_id, recovery_order_id, recovery_payment_id) ──► stage=recovered | recovery_failed
```
Fixed: recovery order bound to the session (B2); stages only move forward, replays get 409 (B3); concurrent reports record once.
Payment reuse across sessions is rejected (P1-3, by the binding).
Still open: no status check on the failure (P2-1); `recovery_failed` can't start a new attempt yet (P1-4); no signature check (P1-5).

### Target (Phases 1–2)
```
order_created
   │ report-failure: payment.status == failed, belongs to order, amount, INR, ID not used before
   ▼
failure_recorded
   │ create-recovery-order: server creates order, stores recovery_order_id in session
   ▼
recovery_order_created
   │ report-recovery: signature valid, payment belongs to the stored recovery_order_id,
   │                   amount, INR, status, payment ID not used before
   ├──► recovered            (final)
   └──► recovery_failed ──► create-recovery-order again while attempts < MAX_ATTEMPTS
```
Every transition is a compare-and-set on the session record. Used payment IDs are kept in a registry.

## 6. Data and provenance

- `RazorpaySource` today: `live_test_mode` (real order created, failure synthetic) and `real_order_tagged_failure` (**no** real order; local ID; failure synthetic). Both names are misleading; P3-4 renames them.
- `outcome_is_simulated`: always `true` for batch results, `false` for live-demo results.
- Amounts are integers in paise; currency INR only.

## 7. Storage

- Keys: `batch:last_results` (no expiry), `live_demo:<order_id>` (TTL `LIVE_DEMO_TTL_SECONDS`, default 3600).
- SQLite file `backend/state.db` by default; Redis when `REDIS_URL` is set (untested).
- Atomic operation (P1-2): `update_atomic(key, fn, ttl)`. SQLite uses `BEGIN IMMEDIATE`; Redis uses `WATCH`/`MULTI` with retry. `fn` may raise to abort without writing.
- No used-payment registry: binding each recovery order to one session (P1-1) plus Razorpay's one-payment-one-order rule already prevents reuse (P1-3, tested).
- Target: Redis/Upstash in deployment (Render's disk is not persistent).

## 8. Configuration

| Variable | Where | Purpose |
|---|---|---|
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | backend `.env` | Test-mode keys (`rzp_test_…`) |
| `ALLOWED_ORIGINS` | backend env | Comma-separated CORS origins; default localhost:5173, 3000 |
| `API_KEY` | backend env | Optional; frontend can't send it (P5-1 replaces this) |
| `REDIS_URL` | backend env | Optional storage backend |
| `SQLITE_PATH` | backend env | Override SQLite location (tests use it) |
| `LIVE_DEMO_TTL_SECONDS` | backend env | Session expiry |
| `VITE_API_BASE` | frontend build env | Backend URL; default `http://localhost:8000` |

## 9. Frontend

- Routing by hand in `App.jsx` (`/`, `/demo`, `/dashboard`, History API). No server rewrite yet → refresh 404 on static hosts (P5-13).
- Views: `Landing.jsx` (+ visual components), `LiveDemo.jsx`, `Dashboard.jsx` (+ `MetricsSection`, `ResultsTable`).
- `RevenueNetworkBackground.jsx`: full-screen canvas on every view.
- API base duplicated in `LiveDemo.jsx` and `Dashboard.jsx`; no shared fetch helper yet (P5-4).

## 10. Deployment (target)

- Backend: Render (or similar), `uvicorn main:app --host 0.0.0.0 --port $PORT`, env vars above, Redis for state, proxy headers trusted for rate limiting.
- Frontend: Vercel, root `frontend`, `VITE_API_BASE` set, `vercel.json` SPA rewrite.
- Never deploy with live Razorpay keys.

## 11. Sources to record

- Razorpay test cards / UPI IDs and their resulting `error_reason`: link here after P2-3.
- Razorpay documented `error_reason` values used by the mapping: link here after P2-2.
