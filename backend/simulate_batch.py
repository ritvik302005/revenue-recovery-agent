"""
Generates a batch of payment records for the recovery agent to act on.

  - Seeded: the same seed gives the same records, ids and (in the agent)
    simulated outcomes.
  - Orders: local order ids by default. With try_live_orders, the first
    MAX_LIVE_ORDERS_PER_BATCH records get a REAL Razorpay test-mode order
    (needs test keys + network); the first failure stops further attempts.
    razorpay_source says which records have a real order.
  - Failure reason + raw_error_code are assigned synthetically, from
    documented Razorpay error codes (razorpay_client.
    DOCUMENTED_ERROR_EXAMPLES), not invented ones.
"""
import logging
import os
import random
from models import PaymentRecord, FailureReason, RazorpaySource
from razorpay_client import DOCUMENTED_ERROR_EXAMPLES, create_real_order

logger = logging.getLogger(__name__)

METHODS = ["card", "upi", "netbanking", "wallet"]
FIRST_NAMES = ["Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Sneha", "Karan",
               "Isha", "Arjun", "Meera", "Rahul", "Divya", "Aditya", "Pooja"]

# ILLUSTRATIVE mix of failure categories (relative weights, not measured
# from real traffic). UNKNOWN is never generated: the batch only uses
# documented Razorpay reasons.
FAILURE_WEIGHTS = {
    FailureReason.CARD_DECLINED: 0.20,
    FailureReason.INSUFFICIENT_FUNDS: 0.16,
    FailureReason.BANK_TIMEOUT: 0.13,
    FailureReason.NETWORK_ERROR: 0.11,
    FailureReason.EXPIRED_CARD: 0.08,
    FailureReason.INVALID_CVV: 0.06,
    FailureReason.INVALID_CARD_DETAILS: 0.04,
    FailureReason.AUTHENTICATION_FAILED: 0.05,
    FailureReason.PAYMENT_CANCELLED: 0.05,
    FailureReason.ISSUER_UNAVAILABLE: 0.06,
    FailureReason.LIMIT_EXCEEDED: 0.04,
    FailureReason.FRAUD_SUSPECTED: 0.02,
}


def _batch_reasons(rng: random.Random, n: int) -> list[FailureReason]:
    """Failure reasons for a batch of n. When n allows it, every category
    appears at least once (so the fraud gate and each policy are always
    exercised); the rest follow FAILURE_WEIGHTS. Shuffled with the seed."""
    categories = list(FAILURE_WEIGHTS.keys())
    weights = list(FAILURE_WEIGHTS.values())
    if n < len(categories):
        return rng.choices(categories, weights=weights, k=n)
    reasons = categories + rng.choices(categories, weights=weights, k=n - len(categories))
    rng.shuffle(reasons)
    return reasons


# Real orders are optional and few: they only show that order creation works,
# and each one is a real (test-mode) API call that can take up to the 8 s timeout.
MAX_LIVE_ORDERS_PER_BATCH = int(os.environ.get("MAX_LIVE_ORDERS_PER_BATCH", 5))


def generate_batch(n: int = 60, seed: int = 42, try_live_orders: bool = False,
                   max_live_orders: int = MAX_LIVE_ORDERS_PER_BATCH) -> list[PaymentRecord]:
    """try_live_orders: create real Razorpay test orders for the first
    max_live_orders records; the first failure stops further attempts, so an
    unreachable Razorpay costs one timeout, not n of them."""
    rng = random.Random(seed)
    reasons = _batch_reasons(rng, n)

    batch = []
    live_attempts = 0
    live_unavailable = None   # set to the error on the first failed call

    for i in range(n):
        name = rng.choice(FIRST_NAMES).lower()
        reason = reasons[i]
        method = rng.choice(METHODS)
        amount = rng.choice([49900, 99900, 149900, 249900, 499900, 999900])  # paise
        # Ids come from the seeded generator too: the simulated outcome is
        # seeded by payment_id, so the same seed reproduces the same batch.
        payment_id = f"pay_{rng.getrandbits(56):014x}"
        order_id = f"order_{rng.getrandbits(56):014x}"

        razorpay_order_id = None
        source = RazorpaySource.LOCAL_ORDER

        if try_live_orders and live_unavailable is None and live_attempts < max_live_orders:
            live_attempts += 1
            try:
                order = create_real_order(amount=amount, receipt=f"batch_{i}")
                razorpay_order_id = order["id"]
                source = RazorpaySource.RAZORPAY_TEST_ORDER
            except Exception as e:
                live_unavailable = e

        taxonomy_entry = DOCUMENTED_ERROR_EXAMPLES[reason]

        record = PaymentRecord(
            payment_id=payment_id,
            order_id=order_id,
            amount=amount,
            razorpay_order_id=razorpay_order_id,
            razorpay_source=source,
            customer_email=f"{name}{i}@example.com",
            customer_contact=f"9{rng.randint(100000000, 999999999)}",
            original_method=method,
            failure_reason=reason,
            raw_error_code=taxonomy_entry["raw_error_code"],
        )
        batch.append(record)

    if live_unavailable is not None:
        logger.warning(
            f"Razorpay order creation failed ({type(live_unavailable).__name__}); stopped trying "
            f"for this batch. The remaining records use local order ids (LOCAL_ORDER). Check "
            f"keys and network access to api.razorpay.com for real test orders."
        )

    return batch


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    batch = generate_batch(60)
    live_count = sum(1 for p in batch if p.razorpay_source == RazorpaySource.RAZORPAY_TEST_ORDER)
    print(f"Generated {len(batch)} records, {live_count} via live Razorpay Orders API.")
    print(batch[0].model_dump_json(indent=2))
