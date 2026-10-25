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

## 2. The live demo, everything real (2–3 min)

Click **Run the live demo**, then **Start the live demo**. You play two people: the merchant's operator (this tab) and the customer (a second tab).

1. **Fail a payment.** The server creates a real ₹10 test order. In Checkout, pay with the failing test card **4100 2800 0009 0000** (any future expiry, any CVV) and choose **Failure** on Razorpay's mock bank page.
2. **The agent decides and acts at once.** The page shows Razorpay's real error. In test mode this card returns the generic `payment_failed` at the `payment_authorization` step (Razorpay's docs say `payment_timed_out`; checked 2026-10-25), which the agent reads as a **card decline**. The action is **suggest alternate method**, and **what the agent did**: it opened a recovery request with **card hidden** and put the message the customer would get by SMS/email into the **Outbox**.
   > "The decision isn't just displayed: it's executed. The customer now has a link, and it won't offer the card that just failed."
3. **Be the customer.** Click **Open as the customer ↗**. A new tab shows the customer's page: the amount, the reason in plain words, **Pay ₹10.00**, and a note that card isn't offered. Pay with UPI **success@razorpay** (or netbanking → any bank → **Success**).
4. **Show re-planning (optional).** Instead of succeeding, choose **Failure** in step 3. The agent escalates to the next action, a **reminder link**: a new outbox message and a new link. After a third failure it opens a support case; after three attempts the gate holds the case.
5. **Verified.** The operator tab updates by itself: **Recovered — verified by Razorpay Test Mode**, with the recovery order id. Point out what that took: the payment is on the order the server created for that link, amount and currency match, Razorpay reports it `captured`, and Checkout's signature (or Razorpay's signed webhook, once deployed) verifies.

> "Nothing here is simulated: a real failure, the agent's real action, a real customer payment, verified with Razorpay."

Worth knowing:
- A failure that maps to **retry with delay** (e.g. a bank outage) gives the customer a link that unlocks after 30 seconds (shortened for the demo).
- An unrecognised reason opens a **support case** and sends the customer nothing to pay.
- After three failed or unpaid links the safety gate **holds** the case, as the batch does.
- If Checkout gets closed by mistake, **Reopen Checkout**; **Cancel and start over** is always there.

Back on the landing page, the receipt and the audit tape now show this real case, stamped by its outcome.

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
