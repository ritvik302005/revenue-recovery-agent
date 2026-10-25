const CHECKOUT_SCRIPT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

// Razorpay's documented test instruments (checked 2026-10-25):
// https://razorpay.com/docs/payments/payments/test-card-details/
// Any future expiry and any CVV work. The error card only fails if
// "Failure" is chosen on the mock bank page. Razorpay's docs say it then
// returns payment_timed_out; in practice (2026-10-25) it returns the generic
// payment_failed at the payment_authorization step, which the agent treats
// as a card decline. The domestic card succeeds with "Success" or any 4–10
// digit OTP. success@razorpay is Razorpay's test UPI ID that succeeds.
export const TEST_CARD_FAIL = { number: '4100 2800 0009 0000', expiry: '12/30', cvv: '123', bankPage: 'choose Failure' }
export const TEST_CARD_SUCCESS = { number: '4100 2800 0000 1007', expiry: '12/30', cvv: '123', bankPage: 'choose Success (or enter any 4–10 digit OTP)' }
export const TEST_UPI_SUCCESS = 'success@razorpay'

export function loadCheckoutScript() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve()
    const script = document.createElement('script')
    script.src = CHECKOUT_SCRIPT_SRC
    script.onload = resolve
    script.onerror = () => reject(new Error('Failed to load Razorpay Checkout script'))
    document.body.appendChild(script)
  })
}
