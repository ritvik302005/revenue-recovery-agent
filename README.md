# AI Revenue Recovery Agent

Built for the Razorpay Buildathon (Track 3). When a Razorpay payment fails, the agent reads the real failure reason, picks a recovery action from a fixed policy, checks it against hard safety rules (fraud holds and a three-attempt retry budget), and records every decision in an audit trail.

The decisions are **rule-based**: a documented error mapping, an action table and a safety gate, orchestrated as a LangGraph graph. There is no ML model or LLM.

> Work in progress: fixes are being made in order from `docs/TASKS.md`.

## What is real and what is simulated

| | Live demo | Batch evaluation |
|---|---|---|
| Order | Real Razorpay test-mode order | A local order id; optionally, real test-mode orders for the first 5 records |
| Failure | Real Checkout failure, real `error_reason` from Razorpay | Synthetic: a documented Razorpay error code assigned by a generator |
| Agent decision | Rule-based, same code as the batch | Rule-based |
| Recovery outcome | **Real**: Razorpay reports the recovery payment `captured`, on a server-created recovery order, with a valid Checkout signature | **Simulated** by a probability model; always labelled `outcome_is_simulated: true` |

The two are never blended into one number.

## Quick start

### Backend (Python 3.11+)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # macOS / Linux
pip install -r requirements.txt
```

Create `backend/.env` with your Razorpay **test-mode** keys (Dashboard → Test Mode → Settings → API Keys):

```
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```

Check the keys and your connection (creates one real ₹10 test order):

```bash
python verify_razorpay_connection.py
```

Run the API (http://localhost:8000, health at `/api/health`):

```bash
uvicorn main:app --reload --port 8000
```

Tests (Razorpay is mocked; no network calls):

```bash
python -m pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:5173 and expects the backend at `http://localhost:8000`; override with `VITE_API_BASE` in `frontend/.env`.

Tests (Vitest + Testing Library; the API and Razorpay Checkout are mocked):

```bash
npm test
```

## Using it

- **Live demo:** follow the on-screen test-card steps. The failing card only fails if you choose **Failure** on Razorpay's mock bank page. Full walkthrough in `docs/DEMO_SCRIPT.md`.
- **Batch evaluation:** set a size and a seed (the same seed reproduces the same run) and click **Run Batch**. Click a row, or focus its payment id and press Enter, to see its audit trail. The headline numbers on the landing page come from 500 seeded runs (`docs/EVALUATION.md`).

## Documentation

| File | Contents |
|---|---|
| `docs/PRD.md` | Product requirements, goals, decisions |
| `docs/ARCHITECTURE.md` | System design, endpoints, live-demo state machine, error mapping and sources |
| `docs/RULES.md` | Rules for working on the project (honesty, payments, secrets, code) |
| `docs/DESIGN.md` | Visual system and the motion / 3D direction |
| `docs/TASKS.md` | The work plan and its status |
| `docs/MEMORY.md` | Running context, decisions and the audit findings |
| `docs/DEMO_SCRIPT.md` | Presentation walkthrough |
| `docs/EVALUATION.md` | The 500-seed batch evaluation and how to reproduce it |

## Safety

Use **test-mode keys only** (`rzp_test_…`); the backend refuses live keys. `backend/.env` is git-ignored and must never be committed.

Endpoints that create orders or run batches need a short-lived session token (the frontend gets one automatically), and real order creation is capped per session and per day. See `docs/ARCHITECTURE.md` §3a.
