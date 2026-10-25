"""
Multi-seed evaluation of the batch simulation.

Runs the same batch the dashboard runs (synthetic failures, rule-based agent,
simulated outcomes) for many seeds, offline (no Razorpay calls), and writes
a summary that is the only source for recovery-rate numbers shown on the
landing page.

Everything here is a SIMULATION: failure reasons are synthetic and outcomes
come from the illustrative RECOVERY_PROBABILITY table. The numbers describe
how the agent's policy behaves under those assumptions, not real recoveries.

Usage (from backend/):
    python evaluate_batch.py                     # 500 seeds x 60 payments (about 8 minutes)
    python evaluate_batch.py --seeds 200 --n 60 --out evaluation/batch_eval.json
"""
import argparse
import json
import logging
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

from models import FailureReason, Outcome
from recovery_agent import run_recovery, MAX_ATTEMPTS
from simulate_batch import generate_batch

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation", "batch_eval.json")


def _percentile(sorted_values: list, q: float) -> float:
    """Linear-interpolated percentile, q in [0, 1]."""
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def evaluate(seeds: range, n: int) -> dict:
    rates, value_shares = [], []
    outcomes = Counter()
    by_category = defaultdict(lambda: {"count": 0, "recovered": 0})
    fraud_holds = max_attempt_stops = total = 0

    for seed in seeds:
        results = [run_recovery(p) for p in generate_batch(n=n, seed=seed, try_live_orders=False)]
        recovered = sum(r.outcome == Outcome.RECOVERED for r in results)
        rates.append(100 * recovered / n)
        value_shares.append(100 * sum(r.amount_recovered for r in results) / sum(r.amount for r in results))
        for r in results:
            total += 1
            outcomes[r.outcome.value] += 1
            cat = by_category[r.failure_reason.value]
            cat["count"] += 1
            cat["recovered"] += r.outcome == Outcome.RECOVERED
            fraud_holds += r.outcome == Outcome.HELD_NO_ACTION
            max_attempt_stops += any(e.step == "safety_check" and "MAX_ATTEMPTS" in e.detail for e in r.audit_trail)

    mean = statistics.fmean(rates)
    sd = statistics.stdev(rates) if len(rates) > 1 else 0.0
    half = 1.96 * sd / math.sqrt(len(rates)) if len(rates) > 1 else 0.0
    ordered = sorted(rates)
    return {
        "kind": "simulated_batch_evaluation",
        "note": "Simulation: synthetic failure reasons (documented Razorpay codes assigned by a generator) "
                "and outcomes from an illustrative probability table. Describes the agent's policy under "
                "those assumptions, not real recoveries.",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seeds": {"first": seeds.start, "last": seeds.stop - 1, "count": len(rates)},
        "batch_size": n,
        "payments_simulated": total,
        "max_attempts": MAX_ATTEMPTS,
        "recovery_rate_pct": {
            "mean": round(mean, 1),
            "sd": round(sd, 1),
            "mean_ci95": [round(mean - half, 1), round(mean + half, 1)],
            "single_run_range95": [round(_percentile(ordered, 0.025), 1), round(_percentile(ordered, 0.975), 1)],
            "min": round(ordered[0], 1),
            "max": round(ordered[-1], 1),
        },
        "value_recovered_pct_mean": round(statistics.fmean(value_shares), 1),
        "outcome_share_pct": {k: round(100 * v / total, 1) for k, v in sorted(outcomes.items())},
        "safety_gate": {
            "fraud_holds": fraud_holds,
            "max_attempt_stops": max_attempt_stops,
        },
        "by_category": {
            cat: {"count": v["count"], "recovery_rate_pct": round(100 * v["recovered"] / v["count"], 1)}
            for cat, v in sorted(by_category.items())
        },
    }


def main():
    logging.disable(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seeds", type=int, default=500, help="number of seeds (1..N)")
    ap.add_argument("--n", type=int, default=60, help="payments per batch")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    result = evaluate(range(1, args.seeds + 1), args.n)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    r = result["recovery_rate_pct"]
    print(f"{result['seeds']['count']} seeds x {args.n} payments ({result['payments_simulated']:,} simulated)")
    print(f"recovery rate: mean {r['mean']}% (95% CI {r['mean_ci95'][0]}-{r['mean_ci95'][1]}%), "
          f"single run 95% range {r['single_run_range95'][0]}-{r['single_run_range95'][1]}%")
    print(f"outcomes: {result['outcome_share_pct']}")
    print(f"safety gate: {result['safety_gate']}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
