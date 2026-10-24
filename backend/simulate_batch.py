"""
Generates a batch of payment records for the recovery agent to act on.

For each record:
  - Tries a REAL call to Razorpay's Orders API to get a genuine
    razorpay_order_id (requires RAZORPAY_KEY_ID/SECRET + network
    access to api.razorpay.com — will only succeed when run outside
    this sandbox, on your own machine).
  - If the live call isn't available (no keys / no network, e.g. when
    running inside a sandboxed dev environment), falls back to a
    locally-generated order_id and marks razorpay_source accordingly
    so the UI/metrics never mislabel it as real.
  - Failure reason + raw_error_code are assigned synthetically, from
    documented Razorpay error codes (razorpay_client.
    DOCUMENTED_ERROR_EXAMPLES), not invented ones.
"""
import random
import logging
from models import PaymentRecord, FailureReason, RazorpaySource
from razorpay_client import DOCUMENTED_ERROR_EXAMPLES, create_real_order

logger = logging.getLogger(__name__)

METHODS = ["card", "upi", "netbanking", "wallet"]
FIRST_NAMES = ["Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Sneha", "Karan",
               "Isha", "Arjun", "Meera", "Rahul", "Divya", "Aditya", "Pooja"]

FAILURE_WEIGHTS = {
    FailureReason.CARD_DECLINED: 0.22,
    FailureReason.INSUFFICIENT_FUNDS: 0.18,
    FailureReason.BANK_TIMEOUT: 0.15,
    FailureReason.NETWORK_ERROR: 0.13,
    FailureReason.EXPIRED_CARD: 0.10,
    FailureReason.INVALID_CVV: 0.08,
    FailureReason.ISSUER_UNAVAILABLE: 0.07,
    FailureReason.LIMIT_EXCEEDED: 0.05,
    FailureReason.FRAUD_SUSPECTED: 0.02,
}


def generate_batch(n: int = 60, seed: int = 42, try_live_orders: bool = True) -> list[PaymentRecord]:
    rng = random.Random(seed)
    reasons = list(FAILURE_WEIGHTS.keys())
    weights = list(FAILURE_WEIGHTS.values())

    batch = []
    live_order_failures = 0

    for i in range(n):
        name = rng.choice(FIRST_NAMES).lower()
        reason = rng.choices(reasons, weights=weights, k=1)[0]
        method = rng.choice(METHODS)
        amount = rng.choice([49900, 99900, 149900, 249900, 499900, 999900])  # paise

        razorpay_order_id = None
        source = RazorpaySource.LOCAL_ORDER

        if try_live_orders:
            try:
                order = create_real_order(amount=amount, receipt=f"batch_{i}")
                razorpay_order_id = order["id"]
                source = RazorpaySource.RAZORPAY_TEST_ORDER
            except Exception as e:
                live_order_failures += 1
                logger.debug(f"Live order creation unavailable ({e}); using local order id.")

        taxonomy_entry = DOCUMENTED_ERROR_EXAMPLES[reason]

        record = PaymentRecord(
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

    if try_live_orders and live_order_failures == n:
        logger.warning(
            f"All {n} live Orders API calls failed (likely no network access to "
            f"api.razorpay.com from this environment, or missing keys). Every record "
            f"uses a locally generated order id (LOCAL_ORDER). Run with network + keys "
            f"for real Razorpay test orders (RAZORPAY_TEST_ORDER)."
        )

    return batch


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    batch = generate_batch(60)
    live_count = sum(1 for p in batch if p.razorpay_source == RazorpaySource.RAZORPAY_TEST_ORDER)
    print(f"Generated {len(batch)} records, {live_count} via live Razorpay Orders API.")
    print(batch[0].model_dump_json(indent=2))
