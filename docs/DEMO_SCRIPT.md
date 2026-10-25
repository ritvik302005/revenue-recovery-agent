# DEMO_SCRIPT.md

A walkthrough for presenting the project (about 5 minutes). Lead with the live demo: it is the part where everything is real. The batch is a simulation and should be presented as one.

## Before you start

- [ ] `backend/.env` has **test-mode** keys (`rzp_test_…`).
- [ ] `python verify_razorpay_connection.py` (from `backend/`) prints a real `order_…` id. Keep the output handy.
- [ ] Backend running: `uvicorn main:app --port 8000` (from `backend/`, venv active).
- [ ] Frontend running: `npm run dev` (from `frontend/`), open http://localhost:5173.
- [ ] The landing page chip says **Razorpay Test Mode keys configured**.

## 1. The problem (30 s)

> "When a payment fails, most systems either don't retry, or retry blindly without knowing why it failed. This agent reads the real failure reason, picks a recovery action from a fixed policy, checks it against hard safety rules, and logs every decision."

Be clear that the decisions are **rule-based** (a lookup table plus a safety gate), orchestrated with LangGraph. There is no ML model or LLM.

## 2. The live demo, everything real (2 min)

Click **Try Real Razorpay Demo**, then **Start Live Demo**.

1. The server creates a real ₹10 test order. In Checkout, pay with the failing test card **4100 2800 0009 0000** (any future expiry, any CVV). On Razorpay's mock bank page, choose **Failure**.
2. The app fetches the failed payment from Razorpay and shows its real `error_reason` (`payment_timed_out` for this card), the category it maps to, the recommended action and the safety-gate result.
3. Click **Attempt Real Recovery**. The **server** creates the recovery order and binds it to this session. Pay with **4100 2800 0000 1007** and choose **Success** (or any 4–10 digit OTP).
4. The result says **Recovered — verified by Razorpay Test Mode**. Point out what that took: Razorpay reports the payment `captured`, it belongs to the recovery order the server created, the amount and currency match, and Checkout's signature verifies.

> "Nothing in this result is simulated. The browser can't pick a different order, replay the result, or claim success: the server checks all of it with Razorpay."

If Checkout gets closed by mistake, click **Reopen Checkout**; **Cancel and start over** is there at every step. If you choose Failure on the recovery attempt instead, the app offers another attempt, up to three. The fourth is blocked by the same safety gate the batch uses.

Back on the landing page, the **Recorded case** card and the audit trail now show this real case.

## 3. The batch evaluation, a simulation (1 min)

Open **View Batch Evaluation** and click **Run Batch**.

> "This runs synthetic failed payments through the same agent. Each failure is a documented Razorpay error code, but assigned by a generator, and whether a recovery succeeds comes from a probability model. It measures the agent's decisions at scale; it is not money recovered."

Point at the provenance chips (real test orders vs local order ids) and the simulated-outcome section. They are never combined into one number.

## 4. One audit trail (45 s)

Click a row with several steps (one that escalated): classify → select action → safety check → execute → replan → safety check → execute. The panel labels the error code as synthetic and the outcome as simulated.

## 5. The fraud safety gate (30 s)

A payment Razorpay declines on a risk check (`payment_risk_check_failed`) is held: no retry, no customer contact. Every batch of 12 or more contains at least one such case, so find the row whose outcome is **held no action** and open its audit trail. Also show a row that ended **still failed**: the safety gate stopped it after three attempts.

## 6. Close (30 s)

> "A real Razorpay integration where a recovery can't be faked, a rule-based agent with hard safety gates and a full audit trail, and a clear line between what's verified and what's simulated."

## If Razorpay is unreachable during the demo

The live demo needs Razorpay; if it fails, the app shows Razorpay's error instead of a result. The batch keeps working: real orders are off by default, and if you tick "Create real Razorpay test orders", only the first 5 records try one and the first failure stops the rest, so a dead connection costs one timeout. The dashboard then says how many orders were real. Say so plainly.
