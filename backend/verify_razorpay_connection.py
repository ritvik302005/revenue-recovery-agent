"""
Minimal sanity check: creates ONE real Razorpay test-mode order and
prints the response. Run this first, on your own machine, after
filling in backend/.env, to confirm your keys + network work before
anything else.

Usage:
    cd backend
    cp .env.example .env      # then paste in your real test keys
    pip install -r requirements.txt
    python verify_razorpay_connection.py
"""
from razorpay_client import create_real_order

if __name__ == "__main__":
    print("Creating a real Razorpay test-mode order for ₹10.00 ...")
    try:
        order = create_real_order(amount=1000, receipt="verify_connection")
        print("\n✅ SUCCESS — real Razorpay Orders API response:\n")
        for k, v in order.items():
            print(f"  {k}: {v}")
        print(f"\nReal order id: {order['id']}")
        print("This confirms your RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET and "
              "network access are working correctly.")
    except Exception as e:
        print(f"\n❌ FAILED: {e}\n")
        print("Checklist:")
        print("  1. Did you copy .env.example to .env and fill in real test keys?")
        print("  2. Are the keys from Test Mode (rzp_test_...), not Live Mode?")
        print("  3. Do you have internet access to api.razorpay.com from this machine?")
