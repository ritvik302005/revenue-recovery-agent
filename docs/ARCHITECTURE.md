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
| `main.py` | All endpoints, CORS, live-demo session logic |
| `access.py` | Session tokens, order budgets (per session and per day; by token or owner id), proxy-aware per-IP rate limits in the shared store (§3a) |
| `executor.py` | `plan_execution`: what an approved action does (request now / after a delay / with a method hidden, reminder, support case); shared by the live demo and the batch (§5) |
| `recovery_agent.py` | Agent graph, action table, safety gate, simulated outcome model |
| `simulate_batch.py` | Seeded synthetic batch; optionally creates real Razorpay orders per record |
| `razorpay_client.py` | SDK client with timeout adapter; `create_real_order`, `fetch_real_payment`, `classify_real_payment_error`; error taxonomy table |
| `models.py` | Enums (`FailureReason`, `RecoveryAction`, `Outcome`, `RazorpaySource`, `LiveDemoStage`), Pydantic models |
| `storage.py` | `set_value` / `get_value` / `delete_value`, optional TTL, `update_atomic`, `purge_expired` |
| `verify_razorpay_connection.py` | Creates one real ₹10 test order to check keys |
| `evaluate_batch.py` | Multi-seed evaluation of the batch simulation (offline); writes `evaluation/batch_eval.json` |
| `tests/` | Safety gate, metrics labelling, live-demo integrity (binding, stages, races, retries, signatures), error mapping and id validation, showcase case |

Frontend files (`frontend/src/`):

| File | Role |
|---|---|
| `App.jsx` | Hand-written routing between the three views (`navigate` accepts `/`, `/demo`, `/dashboard`, `/#section`); skip link |
| `components/SiteNav.jsx` | One nav for every page; real hrefs, routed in-app on plain clicks |
| `components/Landing.jsx` | Landing page: hero, two kinds of evidence, evaluation statement, six controls, audit tape |
| `components/ReceiptPrinter.jsx` | The recorded case printed as a receipt from a CSS-3D printer, with a provenance stamp (`stampFor`); empty and error states (DESIGN.md §2, §5) |
| `components/AuditTrailVisual.jsx` | That case's real audit trail, as a printed tape |
| `components/AgentJourney.jsx` | The six controls as an accessible tab list (arrow keys, no autoplay) |
| `components/HeadlineMetrics.jsx` | The `GET /api/evaluation` result as a statement with dotted leaders |
| `components/LiveDemo.jsx` | Live Razorpay Checkout flow: progress steps, test-card panels, result slip |
| `components/Dashboard.jsx`, `MetricsSection.jsx`, `ResultsTable.jsx` | Batch evaluation |
| `hooks/useShowcaseCase.js`, `useHealth.js`, `useEvaluation.js`, `useCountUp.js`, `useReveal.js`, `usePointerTilt.js` | Data and animation hooks |
| `index.css` | The single design system (tokens on `:root`, single-class selectors); see `docs/DESIGN.md` |
| `api.js` | `API_BASE` and `apiFetch`, the only place that calls `fetch`; errors are `ApiError` with a displayable message; `session: true` gets, sends and renews the session token (memory only) |

## 3. Endpoints (current)

| Method | Path | Auth | Rate limit | Calls Razorpay | Notes |
|---|---|---|---|---|---|
| GET | `/api/health` | – | – | no | `razorpay_keys_configured` (true only for test keys), `razorpay_key_mode` (`test` / `live` / `unknown` / null, from the prefix), `storage_backend`, and `razorpay_last_success_at` / `_last_failure_at` / `_last_failure_kind` (`rejected` or `unreachable_or_error`), recorded by every real Razorpay call (`razorpay_client._tracked`, key `health:razorpay`). Never probes Razorpay itself |
| POST | `/api/session` | – | 10/min/IP | no | Issues `{token, expires_in, orders_per_session}`; send the token as `X-Session-Token` |
| POST | `/api/batch/run?n&try_live_orders&seed` | session | 10/min/IP | only if `try_live_orders`: at most `MAX_LIVE_ORDERS_PER_BATCH` (5) orders, within the session and daily budget, stopping at the first failure | n ≤ 500; synchronous; `try_live_orders` defaults to false; with no budget left the batch still runs on local ids; `seed` (default 42) makes the batch and its simulated outcomes reproducible; returned with the results and in metrics |
| GET | `/api/batch/results` | – | – | no | Last batch from storage |
| GET | `/api/batch/metrics` | – | – | no | 404 before first batch |
| GET | `/api/evaluation` | – | – | no | The committed multi-seed evaluation (`backend/evaluation/batch_eval.json`, made by `evaluate_batch.py`); 404 if not generated. The only source of headline recovery numbers |
| GET | `/api/showcase/case` | – | – | no | One real recorded case for the landing page: latest live-demo result (`kind: live_demo`), else a batch record (`kind: batch_record`, labelled synthetic failure + simulated outcome), else `{"kind": "none"}` |
| GET | `/api/live-demo/config` | – | – | no | Returns public `key_id`; `configured` is false for live-mode keys (`get_client` refuses `rzp_live_` keys) |
| POST | `/api/live-demo/create-order` | session | 10/min/IP | yes (1 order from the budget; refunded if Razorpay fails) | ₹1–₹1,000, receipt generated server-side; the session record stores the token's owner id |
| POST | `/api/live-demo/report-failure?order_id&payment_id` | session, owner | 30/min/IP | yes (fetch) | Checks order/amount/INR and `status == "failed"` (`created`/`authorized` → 409; else 400), then classify → decide → gate → **execute** (§5). Stage `order_created` → `awaiting_customer` / `escalated` / `held`. Returns the operator view |
| GET | `/api/live-demo/session?order_id` | session, owner | 30/min/IP | no | Operator view: stage, decision, attempts, current request, outbox, support case, result, audit trail. Polled while the customer holds a request; notices an expired request (counts as a failed attempt) |
| GET | `/api/recover/{token}` | token only | 30/min/IP | no | The customer's view of a recovery request: amount, plain reason, status (`scheduled` / `open` / `paid` / `failed` / `expired` / `superseded` / `escalated`), countdown, hidden method, Checkout config |
| POST | `/api/recover/{token}/order` | token only | 10/min/IP | yes (1 order from the **demo session's** budget) | Creates the request's Razorpay order once (idempotent; a race refunds the loser); 409 while scheduled or once inactive; 410 if the demo session has expired |
| POST | `/api/recover/{token}/report?payment_id&razorpay_signature` | token only | 30/min/IP | yes (fetch) | Settles the request: payment must be on the request's order, amount, INR; non-final → 409; captured needs Checkout's signature for that order (400 otherwise) → `recovered`; failed → re-plan (§5) |
| POST | `/api/webhooks/razorpay` | `X-Razorpay-Signature` | – | no | HMAC-SHA256 of the raw body with `RAZORPAY_WEBHOOK_SECRET` (400 if invalid; 503 if unset); de-duplicated by `X-Razorpay-Event-Id`. `payment.failed` on a demo order → same as report-failure; `payment.captured` / `order.paid` / `payment.failed` on a recovery order → settle. A 409 from the other path → `already_recorded`; a mismatched payment → logged, `rejected` (200) |

Out-of-order or repeated calls return **409**; unknown sessions **404**. Order and payment ids are validated on every live-demo endpoint (`^order_[A-Za-z0-9]{1,40}$`, `^pay_[A-Za-z0-9]{1,40}$`; signature ≤ 128 chars) → **422** before any Razorpay call. Every stage change is an atomic read-check-write (`storage.update_atomic`).

### 3a. Access and rate limits (P5-1, P5-2)

- **Session tokens** replace the old static `X-API-Key`, which a browser couldn't keep secret. `POST /api/session` returns a random token (`secrets.token_urlsafe(32)`), valid `ACCESS_SESSION_TTL_SECONDS` (30 min). Only its SHA-256 is stored (`access:<hash>`). Missing, unknown or expired token → **401**; the frontend then gets a new token and retries once.
- **Ownership:** a live-demo session stores the creating token's hash; every later step from another token → **403**, before any Razorpay call.
- **Order budgets:** each token may create `ORDERS_PER_SESSION` (10) real orders; the whole server `MAX_LIVE_ORDERS_PER_DAY` (200, key `cap:live_orders:<UTC date>`). Exhausted → **429** with no Razorpay call. A failed Razorpay call gives its slot back. Batches take up to 5 slots and run with however many they get.
- **Rate limits:** fixed one-minute windows per client IP and scope (`session`, `orders`, `reports`, `batches`), counted with `update_atomic` in the shared store, so they hold across workers and restarts (Redis when configured). The client IP comes from `X-Forwarded-For` only when `TRUSTED_PROXY_HOPS` > 0, taking that many entries from the right (entries further left can be forged). Default 0 = the socket address.
- **Bot check (Cloudflare Turnstile):** when `TURNSTILE_SECRET_KEY` is set, `POST /api/session` needs `{"turnstile_token"}` that Cloudflare's siteverify accepts (single use, 5 min; optional `TURNSTILE_HOSTNAMES` allow-list); missing or rejected → 403, Cloudflare unreachable → 503 (fails closed). Frontend: `turnstile.js` + `<HumanCheck />` on the dashboard and live demo, `appearance: interaction-only` (invisible unless Cloudflare wants a click); `apiFetch` takes a token whenever it needs a new session. Off when the keys are unset (tests, local dev). Checked on localhost with real keys: an automated browser is shown the "Verify you are human" checkbox and gets no token.

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

Since Phase 7 the agent's decision is **executed**, and the customer (not the operator) pays what it sent.

```
create-order ──► order_created ──► operator's Checkout (failing test card) ──► payment.failed
   │ report-failure (browser)  or  payment.failed webhook (Razorpay)
   ▼  classify → select_action → safety_check → EXECUTE (executor.plan_execution)
   ├─ fraud ─────────────────────────────────────────────► held (final)
   ├─ escalate_to_support ──► support case, no payment ───► escalated (final)
   └─ retry / delay / alternate / reminder ──► recovery request rr_<token> + outbox message
        ▼
   awaiting_customer ── customer opens /recover/<token> ── POST order (once) ── Checkout
        │ report (Checkout signature)  or  payment.captured / order.paid webhook
        ├─ captured ──────────────────────────────────────► recovered (final)
        └─ failed, or request expired unpaid ──► replan: next action → safety_check
             ├─ attempts < 3 ──► new request (or support case) ──► awaiting_customer / escalated
             └─ attempts = 3 ──────────────────────────────► held (final)
```

- **Executor** (`executor.py`): `plan_execution(action, amount, failed_method)` → `ExecutionPlan` (kind, delay, hidden method, customer message, audit summary). `retry_with_delay` waits `RECOVERY_DELAY_SECONDS` (30 s demo); `suggest_alternate_method` hides Razorpay's `payment.method` of the failed payment via Checkout `config.display.hide`; `escalate_to_support` opens a case and sends nothing. The batch uses the same function and only records the plan.
- **Recovery requests** live inside the session record (`requests[token]`, `current_request`), so every change is one atomic update. Token: `rr_` + 24 random bytes (URL-safe); the token is the customer's only access; never written whole into the audit trail or showcase. One Razorpay order per request, created only when the customer opens it. Unpaid requests expire after `RECOVERY_REQUEST_TTL_SECONDS` (noticed lazily by the next read) and count as a failed attempt.
- **Re-planning**: the batch's escalation chain (`recovery_agent.next_action`): retry → alternate method → reminder → support; delay → alternate method. The safety gate runs before each execution and holds the case at 3 attempts.
- **Verification**: a capture counts only with Checkout's signature for the request's order (`verify_checkout_signature`, HMAC-SHA256 of `order_id|payment_id`) or a signed webhook. Checkout's report and the webhook race safely: the first settles the request, the second gets 409 / `already_recorded`.
- Kept from Phases 1–2: server-bound orders (B2), forward-only stages with 409 on replays (B3), no payment reuse (P1-3, by the binding), concurrent reports record once, only `status == "failed"` starts a recovery (B1).
- The demo **outbox** stands in for SMS/email (owner's decision): messages are stored with the session and shown to the operator with "Open as the customer". Payment Links were not used: test mode caps them at 30 per business and they can't hide a method.

## 6. Data and provenance

- `RazorpaySource` (P3-4): `razorpay_test_order` (a real order created via Razorpay's test-mode Orders API) or `local_order` (no Razorpay call; local id). The failure reason is synthetic in both. Metrics: `razorpay_data_provenance.razorpay_test_orders` / `.local_orders`.
- `outcome_is_simulated`: always `true` for batch results, `false` for live-demo results.
- Amounts are integers in paise; currency INR only.

### Errors shown to the browser (P5-3)

- A failed Razorpay call goes through `_razorpay_error(action, e)` in `main.py`: the full exception is logged server-side; the browser gets 502 with Razorpay's own description for a `BadRequestError` ("Razorpay said: …"), 503 when test keys aren't configured (`RazorpayNotConfigured`), and a fixed "unreachable or returned an error" message for anything else. Raw exception text is never returned.
- `storage.py` logs `REDIS_URL` without its user:password part, and only the exception type on a Redis connection failure.

## 7. Storage

- Keys: `batch:last_results` (no expiry), `live_demo:<order_id>` (TTL `LIVE_DEMO_TTL_SECONDS`, default 3600), `showcase:latest_live_case` (no expiry; snapshot written when a session reaches `recovered`, `escalated` or `held`), `recovery_token:<token>` → session order id and `recovery_order:<razorpay order id>` → token (TTL as the session), `webhook_event:<event id>` (2 days, de-duplication), `health:razorpay`, `access:*`, `cap:live_orders:*`, `ratelimit:*`.
- SQLite file `backend/state.db` by default; Redis when `REDIS_URL` is set (`redis` is in requirements; the Redis branch is tested against fakeredis in `tests/test_storage_redis.py`, not yet against a real Upstash instance). `/api/health` reports which backend is live, so a silent fallback to SQLite is visible.
- Atomic operation (P1-2): `update_atomic(key, fn, ttl)`. SQLite uses `BEGIN IMMEDIATE`; Redis uses `WATCH`/`MULTI` with retry. `fn` may raise to abort without writing.
- No used-payment registry: binding each recovery order to one session (P1-1) plus Razorpay's one-payment-one-order rule already prevents reuse (P1-3, tested).
- Target: Redis/Upstash in deployment (Render's disk is not persistent).

## 8. Configuration

| Variable | Where | Purpose |
|---|---|---|
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | backend `.env` | Test-mode keys (`rzp_test_…`) |
| `ALLOWED_ORIGINS` | backend env | Comma-separated CORS origins; default localhost:5173, 3000 |
| `ACCESS_SESSION_TTL_SECONDS` | backend env | Session token lifetime (default 1800) |
| `ORDERS_PER_SESSION` | backend env | Real orders one token may create (default 10) |
| `MAX_LIVE_ORDERS_PER_DAY` | backend env | Server-wide daily cap on real orders (default 200) |
| `TRUSTED_PROXY_HOPS` | backend env | Proxies in front of the app whose `X-Forwarded-For` entries are trusted (default 0; usually 1 behind a platform proxy, to be verified against the real host's headers at deploy) |
| `REDIS_URL` | backend env | Optional storage backend |
| `SQLITE_PATH` | backend env | Override SQLite location (tests use it) |
| `LIVE_DEMO_TTL_SECONDS` | backend env | Session expiry |
| `MAX_LIVE_ORDERS_PER_BATCH` | backend env | Cap on real test orders per batch when `try_live_orders` is on (default 5) |
| `EVALUATION_PATH` | backend env | Override the evaluation JSON served by `/api/evaluation` |
| `RECOVERY_DELAY_SECONDS` | backend env | Wait before a `retry_with_delay` request becomes payable (default 30, shortened for the demo) |
| `RECOVERY_REQUEST_TTL_SECONDS` | backend env | How long a recovery request stays payable before it counts as unpaid (default 1800) |
| `RAZORPAY_WEBHOOK_SECRET` | backend env | Secret of the test-mode webhook set in the Razorpay Dashboard (not the API secret); unset → the webhook endpoint returns 503 |
| `TURNSTILE_SECRET_KEY` | backend env | Cloudflare Turnstile secret; set → sessions need a valid Turnstile token |
| `TURNSTILE_HOSTNAMES` | backend env | Optional comma-separated hostnames the token must be solved on (e.g. the Vercel domain) |
| `VITE_API_BASE` | frontend build env | Backend URL; default `http://localhost:8000` |
| `VITE_TURNSTILE_SITE_KEY` | frontend build env | Turnstile site key (public); unset → no widget |

## 9. Frontend

- Routing by hand in `App.jsx` (`/`, `/demo`, `/dashboard`, `/recover/<token>`, History API). `frontend/vercel.json` rewrites every path to `index.html`, so a refresh or an opened recovery link works on Vercel (P5-13).
- Views: `Landing.jsx`, `LiveDemo.jsx` (operator: fail a payment, then the agent panel, outbox and result; polls the session), `RecoverPage.jsx` (the customer's recovery link: countdown, Checkout with the failed method hidden, verified result), `Dashboard.jsx`.
- `checkout.js` loads Razorpay Checkout and holds the documented test instruments.

## 10. Deployment (target)

- Backend: Render (or similar), `uvicorn main:app --host 0.0.0.0 --port $PORT`, env vars above, Redis for state, proxy headers trusted for rate limiting. Add a **test-mode webhook** in the Razorpay Dashboard pointing at `https://<backend>/api/webhooks/razorpay` with events `payment.failed`, `payment.captured`, `order.paid`, and set `RAZORPAY_WEBHOOK_SECRET`.
- Frontend: Vercel, root `frontend`, `VITE_API_BASE` set, `vercel.json` SPA rewrite.
- Never deploy with live Razorpay keys.

## 11. Error mapping and sources

`razorpay_client.ERROR_REASON_TO_CATEGORY` maps Razorpay's documented `error_reason` values to our `FailureReason` categories; the live demo uses it, and the batch labels records with `DOCUMENTED_ERROR_EXAMPLES` (one documented code per category, assigned synthetically). Undocumented or unspecific reasons (incl. `payment_failed`) → `unknown` → escalate to support. Razorpay has no "fraud" reason; `payment_risk_check_failed` → `fraud_suspected` → safety-gate hold.

Sources (checked 2026-10-25):
- Payment error reasons: https://razorpay.com/docs/errors/payments/list/
- Test cards and the error each produces: https://razorpay.com/docs/payments/payments/test-card-details/
  - Error cards fail only if you choose **Failure** on the mock bank page. Any future expiry, any CVV; OTP of 4–10 digits succeeds, fewer than 4 fails.
  - The page spells it `insufficient_fund`; the error list spells it `insufficient_funds`. Both are mapped.
  - **Observed, 2026-10-25:** card `4100 2800 0009 0000` (listed as `payment_timed_out`) actually returns `error_reason: payment_failed`, `error_source: gateway`, `error_step: payment_authorization`. `classify_real_payment_error` therefore treats a generic `payment_failed` on a **card** at the **authorization** step as `card_declined` (raw code gets ` @ payment_authorization`); any other generic failure stays `unknown` → escalate. The policy preview has no step, so `payment_failed` previews as unknown.
