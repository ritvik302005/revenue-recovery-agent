# ARCHITECTURE.md

How the system is built **today** (verified by the audit of 2026-10-24) and the **target** after Phases 1–5. Update the "Current" sections as tasks land; when a target item is done, move it up.

> This file is the authoritative architecture doc. The old root-level `ARCHITECTURE.md`, `PROJECT_STRUCTURE.md` and `EVALUATION_REPORT.md` were removed in P3-7 (they were partly wrong; still in git history). An evaluation doc with real numbers follows the multi-seed run (P4-4).

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
| `evaluate_batch.py` | Multi-seed evaluation of the batch simulation (offline); writes `evaluation/batch_eval.json` |
| `tests/` | Safety gate, metrics labelling, live-demo integrity (binding, stages, races, retries, signatures), error mapping and id validation, showcase case |

Frontend files (`frontend/src/`):

| File | Role |
|---|---|
| `App.jsx` | Hand-written routing between the three views |
| `api.js` | `API_BASE` from `VITE_API_BASE` |
| `components/Landing.jsx` | Landing page: hero, status chip, recorded case, agent journey, audit trail, real vs simulated |
| `components/RecordedCaseCard.jsx` | The real recorded case (or empty state) in the hero |
| `components/AuditTrailVisual.jsx` | That case's real audit trail |
| `components/AgentJourney.jsx` | Six-step explanation of the agent's controls |
| `components/HeadlineMetrics.jsx` | Headline numbers (hardcoded until P3-1) |
| `components/LiveDemo.jsx` | Live Razorpay Checkout flow |
| `components/Dashboard.jsx`, `MetricsSection.jsx`, `ResultsTable.jsx` | Batch evaluation |
| `components/RevenueNetworkBackground.jsx` | Animated canvas background |
| `hooks/useShowcaseCase.js`, `useHealth.js`, `useCountUp.js`, `useReveal.js` | Data and animation hooks |

## 3. Endpoints (current)

| Method | Path | Auth | Rate limit | Calls Razorpay | Notes |
|---|---|---|---|---|---|
| GET | `/api/health` | – | – | no | `razorpay_live_connectivity` is a fixed `"unverified"` |
| POST | `/api/batch/run?n&try_live_orders&seed` | API key if set | 10/min/IP | only if `try_live_orders`, at most `MAX_LIVE_ORDERS_PER_BATCH` (5) orders, stopping at the first failure | n ≤ 500; synchronous; `try_live_orders` defaults to false; `seed` (default 42) makes the batch and its simulated outcomes reproducible; returned with the results and in metrics |
| GET | `/api/batch/results` | – | – | no | Last batch from storage |
| GET | `/api/batch/metrics` | – | – | no | 404 before first batch |
| GET | `/api/evaluation` | – | – | no | The committed multi-seed evaluation (`backend/evaluation/batch_eval.json`, made by `evaluate_batch.py`); 404 if not generated. The only source of headline recovery numbers |
| GET | `/api/showcase/case` | – | – | no | One real recorded case for the landing page: latest live-demo result (`kind: live_demo`), else a batch record (`kind: batch_record`, labelled synthetic failure + simulated outcome), else `{"kind": "none"}` |
| GET | `/api/live-demo/config` | – | – | no | Returns public `key_id` |
| POST | `/api/live-demo/create-order` | API key if set | 10/min/IP | yes | ₹1–₹1,000, receipt generated server-side |
| POST | `/api/live-demo/report-failure?order_id&payment_id` | API key if set | **none** | yes | Stage `order_created` → `failure_recorded` / `held`; checks order/amount/INR; payment status must be `failed` (`created`/`authorized` → 409 not final; anything else → 400) |
| POST | `/api/live-demo/create-recovery-order?order_id` | API key if set | 10/min/IP | yes | Stage `failure_recorded` or `recovery_failed` → `recovery_order_created`; runs `safety_check` with `recovery_attempts` first (≥ 3 → stage `held`, 409, no order); server creates the order for the original amount and stores `current_recovery_order_id` |
| POST | `/api/live-demo/report-recovery?order_id&recovery_order_id&recovery_payment_id&razorpay_signature` | API key if set | **none** | yes | Stage `recovery_order_created` → `recovered` / `recovery_failed`; `recovery_order_id` must equal the stored one; non-final payment status → 409 without recording; a **captured** payment needs a valid Checkout signature (400 otherwise); failed attempts need none |

Out-of-order or repeated calls return **409**; unknown sessions **404**. Order and payment ids are validated on every live-demo endpoint (`^order_[A-Za-z0-9]{1,40}$`, `^pay_[A-Za-z0-9]{1,40}$`; signature ≤ 128 chars) → **422** before any Razorpay call. Every stage change is an atomic read-check-write (`storage.update_atomic`).

## 4. Agent

Graph: `classify → select_action → safety_check → execute → (should_replan) → escalate → safety_check …`

All decisions are fixed rules; there is no ML model or LLM.

- **classify**: in the batch, logs the (synthetic) failure reason already on the record; in the live demo, the reason comes from `classify_real_payment_error` (§11).
- **select_action**: fixed table, failure reason → action (`unknown` → escalate to support).
- **safety_check** (before every execution): fraud → `NO_ACTION_FRAUD_HOLD` / `HELD_NO_ACTION`, stop. `attempt_count ≥ 3` → `NO_ACTION_MAX_ATTEMPTS` / `STILL_FAILED`, stop.
- **execute**: `attempt_count += 1`; success if `random.Random(f"{payment_id}-{attempt}") < RECOVERY_PROBABILITY[(reason, action)]` (illustrative, default 0.25). Success → `RECOVERED`, done. Support failing → `PENDING_CUSTOMER_ACTION` (handed to a human), done. Anything else failing, including an unpaid reminder link → `STILL_FAILED`.
- **should_replan**: `STILL_FAILED` → escalate and go back through `safety_check`, which stops the loop once the budget is used.
- **escalate**: retry_same → alternate method → reminder link → support; retry_with_delay → alternate method.

Measured (P4-2, 200 seeds × 60, before P4-3): all four outcomes occur (recovered 8,476; pending 2,102; still failed 1,195; held 227 of 12,000), and the max-attempts gate fired 1,195 times. Before P4-2: only recovered/pending, gate never fired.

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
Retries (P1-4): from `recovery_failed`, `create-recovery-order` starts a new attempt; `report-recovery` counts `recovery_attempts`; the agent's `safety_check` blocks attempt 4 (stage `held`, logged in the audit trail). The response carries `recovery_attempts` and `max_attempts`.
Signatures (P1-5): `razorpay_client.verify_checkout_signature` (SDK `utility.verify_payment_signature`: HMAC-SHA256 of `order_id|payment_id` with the key secret, constant-time compare, no API call). Required before a captured recovery is recorded; Razorpay's `payment.failed` event carries no signature, so failed attempts are recorded from the fetched status alone.
Failure status (P2-1): `report-failure` accepts only `status == "failed"`; a captured payment can no longer be recorded as a failure (B1).

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

- `RazorpaySource` (P3-4): `razorpay_test_order` (a real order created via Razorpay's test-mode Orders API) or `local_order` (no Razorpay call; local id). The failure reason is synthetic in both. Metrics: `razorpay_data_provenance.razorpay_test_orders` / `.local_orders`.
- `outcome_is_simulated`: always `true` for batch results, `false` for live-demo results.
- Amounts are integers in paise; currency INR only.

## 7. Storage

- Keys: `batch:last_results` (no expiry), `live_demo:<order_id>` (TTL `LIVE_DEMO_TTL_SECONDS`, default 3600), `showcase:latest_live_case` (no expiry; snapshot written when a session reaches `recovered`, `recovery_failed` or `held`).
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
| `MAX_LIVE_ORDERS_PER_BATCH` | backend env | Cap on real test orders per batch when `try_live_orders` is on (default 5) |
| `EVALUATION_PATH` | backend env | Override the evaluation JSON served by `/api/evaluation` |
| `VITE_API_BASE` | frontend build env | Backend URL; default `http://localhost:8000` |

## 9. Frontend

- Routing by hand in `App.jsx` (`/`, `/demo`, `/dashboard`, History API). No server rewrite yet → refresh 404 on static hosts (P5-13).
- Views: `Landing.jsx` (+ visual components), `LiveDemo.jsx`, `Dashboard.jsx` (+ `MetricsSection`, `ResultsTable`).
- Landing case (P3-2): `hooks/useShowcaseCase.js` fetches `/api/showcase/case` (and again when the tab becomes visible); `RecordedCaseCard.jsx` (hero) and `AuditTrailVisual.jsx` render it, with loading / error / empty states. `src/api.js` holds `API_BASE` (Dashboard and LiveDemo still define their own until P5-4).
- `RevenueNetworkBackground.jsx`: full-screen canvas on every view.
- API base duplicated in `LiveDemo.jsx` and `Dashboard.jsx`; no shared fetch helper yet (P5-4).

## 10. Deployment (target)

- Backend: Render (or similar), `uvicorn main:app --host 0.0.0.0 --port $PORT`, env vars above, Redis for state, proxy headers trusted for rate limiting.
- Frontend: Vercel, root `frontend`, `VITE_API_BASE` set, `vercel.json` SPA rewrite.
- Never deploy with live Razorpay keys.

## 11. Error mapping and sources

`razorpay_client.ERROR_REASON_TO_CATEGORY` maps Razorpay's documented `error_reason` values to our `FailureReason` categories; the live demo uses it, and the batch labels records with `DOCUMENTED_ERROR_EXAMPLES` (one documented code per category, assigned synthetically). Undocumented or unspecific reasons (incl. `payment_failed`) → `unknown` → escalate to support. Razorpay has no "fraud" reason; `payment_risk_check_failed` → `fraud_suspected` → safety-gate hold.

Sources (checked 2026-10-25):
- Payment error reasons: https://razorpay.com/docs/errors/payments/list/
- Test cards and the error each produces: https://razorpay.com/docs/payments/payments/test-card-details/
  - Error cards fail only if you choose **Failure** on the mock bank page. Any future expiry, any CVV; OTP of 4–10 digits succeeds, fewer than 4 fails.
  - The page spells it `insufficient_fund`; the error list spells it `insufficient_funds`. Both are mapped.
