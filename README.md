# AI Revenue Recovery Agent — Razorpay Buildathon (Track 3)

Detects payment failures, diagnoses root cause, executes a bounded
recovery workflow via a LangGraph agent (classify → select action →
hard safety gate → execute → replan/escalate), and reports results
with a full audit trail — with real Razorpay data and simulated
recovery outcomes kept strictly, visibly separate throughout.

## Documentation index

| Document | What's in it |
|---|---|
| **README.md** (this file) | Quick start, doc index |
| [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) | Full file tree, one-line responsibility per file |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Agent flow, sequence diagrams, safety gates, every API endpoint documented |
| [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) | Step-by-step walkthrough for presenting to judges |
| [`EVALUATION_REPORT.md`](./EVALUATION_REPORT.md) | **Read this one closely** — exact verified vs simulated breakdown, known limitations, Razorpay connectivity verification steps, Render/Vercel deployment instructions |

## What's real vs simulated (short version — see EVALUATION_REPORT.md for the full breakdown)

- **Real**: order creation via Razorpay's actual Orders API (when run
  with your test keys + network), and all failure reasons/error codes
  come from Razorpay's own documented error taxonomy — not invented.
- **Simulated, always labeled**: whether a recovery action actually
  succeeds. Razorpay test mode can't headlessly simulate a customer
  retrying — that requires a human clicking Success/Failure on their
  mock bank page. Every result carries `outcome_is_simulated: true`,
  and the UI keeps "Data Provenance (Real)" visually separate from
  "Simulated Recovery Outcomes" — never blended into one number.

## Quick start

### 1. Backend

```bash
cd backend
cp .env.example .env
# edit .env: paste your RAZORPAY_KEY_ID (starts rzp_test_...) and RAZORPAY_KEY_SECRET
pip install -r requirements.txt

# Verify your Razorpay connection first (one real order, ₹10):
python verify_razorpay_connection.py

# Then run the API:
uvicorn main:app --reload --port 8000
```

Backend runs at http://localhost:8000. Check http://localhost:8000/api/health.

Full verification steps (with expected output) are in
`EVALUATION_REPORT.md §6`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard runs at http://localhost:5173 (Vite will print the exact URL).
It expects the backend at `http://localhost:8000` by default — override
with a `.env` file containing `VITE_API_BASE=http://your-backend-url`.

## Using it

1. Open the dashboard, set a batch size (default 60), click **Run Batch**.
2. The backend generates that many synthetic failed payments (weighted
   across realistic Razorpay error categories), tries a real Orders API
   call for each (falls back gracefully + labels itself if that fails),
   then runs the LangGraph recovery agent on all of them.
3. Metrics split into **Data Provenance (Real)** and **Simulated Recovery
   Outcomes** — always visually separate.
4. Click any row in the results table to see the full step-by-step audit
   trail for that payment (classify → select action → safety check →
   execute → any replan/escalation).

For the full endpoint reference, sequence diagrams, and safety-gate
logic, see `ARCHITECTURE.md`. For known limitations and what's still
unverified, see `EVALUATION_REPORT.md §5`.

## Deployment

Backend → Render, frontend → Vercel. Full step-by-step instructions
(build commands, env vars, post-deploy checklist) are in
`EVALUATION_REPORT.md §7`.
