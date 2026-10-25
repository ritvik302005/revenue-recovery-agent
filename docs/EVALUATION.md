# EVALUATION.md

Multi-seed evaluation of the **batch simulation**. Source: `backend/evaluation/batch_eval.json`, produced by `backend/evaluate_batch.py` (served at `GET /api/evaluation`). Regenerate after any change to the agent, the probability table or the batch generator.

## What this measures, and what it doesn't

This is a simulation. Each payment's failure reason is a documented Razorpay error code **assigned by a generator**, and whether a recovery action succeeds is drawn from an **illustrative** probability table (`RECOVERY_PROBABILITY` in `recovery_agent.py`), not from real data. The numbers therefore describe how the agent's policy (action table, escalation, safety gate) behaves **under those assumptions**. They are not real recovery rates and must never be presented as money recovered.

Real recoveries are only shown by the live demo, one payment at a time.

## Setup

- 500 seeds (1–500), 60 payments each: 30,000 simulated payments.
- Every batch contains each of the 12 documented failure categories at least once (P4-3).
- Retry budget: 3 attempts. No Razorpay calls (local order ids).
- Generated 2026-10-25.

## Results

**Recovery rate (share of payments ending `recovered`)**

| Statistic | Value |
|---|---|
| Mean across seeds | **68.3%** |
| 95% confidence interval of the mean | 67.8% – 68.8% |
| A single 60-payment run, 95% range | **56.7% – 78.3%** |
| Lowest / highest single run | 51.7% / 90.0% |
| Standard deviation between runs | 5.8 points |

A single dashboard run can land anywhere from the high 50s to the high 70s, so one run's rate is not a meaningful headline on its own.

**Outcome mix**

| Outcome | Share |
|---|---|
| Recovered | 68.3% |
| Pending (handed to support) | 16.9% |
| Still failed (stopped by the max-attempts gate) | 11.5% |
| Held (fraud / risk check) | 3.3% |

**Safety gate:** 980 fraud holds and 3,458 max-attempt stops across the 30,000 payments. Every fraud case was held (recovery rate 0%).

**By failure category**

| Category | Payments | Recovered |
|---|---|---|
| network error | 3,140 | 82.6% |
| bank timeout | 3,589 | 80.1% |
| expired card | 2,420 | 77.0% |
| card declined | 5,232 | 75.3% |
| authentication failed | 1,788 | 73.9% |
| invalid card details | 1,487 | 71.6% |
| limit exceeded | 1,514 | 71.3% |
| issuer unavailable | 1,869 | 67.1% |
| invalid CVV | 1,945 | 64.2% |
| insufficient funds | 4,351 | 54.1% |
| payment cancelled | 1,685 | 52.5% |
| fraud suspected | 980 | 0.0% |

The per-category differences follow directly from the illustrative probabilities and the escalation chain each category starts on; they are a property of the assumptions, not a finding about real payments.

## Reproducing

```bash
cd backend
python evaluate_batch.py                 # 500 seeds x 60, about 8 minutes
python evaluate_batch.py --seeds 50      # quicker check
```

Any single seed can also be replayed in the dashboard (Seed field) or via `POST /api/batch/run?seed=<n>`; the evaluation and the dashboard use the same code, which `tests/test_evaluation.py` checks.
