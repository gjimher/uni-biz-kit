import json

from ....context import Context


def generate(ctx: Context) -> str:
    """Payment helpers for custom presentation pages.

    Wraps the generated `payment` edge function (Stripe proxy with a dev-mode
    simulator). When system.json has no `payments` section a disabled stub is
    emitted so pages can feature-detect with `paymentsEnabled`.
    """
    payments = ctx.system_config.get("payments")
    if not payments:
        return """// Payments are not configured for this app (no `payments` section in system.json).
export const paymentsEnabled = false;
export const paymentsDevMode = false;

const notConfigured = () => { throw new Error('Payments are not configured'); };
export const createPaymentIntent = notConfigured;
export const confirmPayment = notConfigured;
export const getPaymentStatus = notConfigured;
"""

    dev_mode = json.dumps(payments["dev_mode"])
    provider = json.dumps(payments["provider"])
    currency = json.dumps(payments["currency"])
    return f"""import {{ supabaseClient }} from '../../supabaseClient';

// Payment configuration from system.json (payments section).
export const paymentsEnabled = true;
export const paymentsDevMode = {dev_mode};
export const paymentsProvider = {provider};
export const paymentsCurrency = {currency};

// Invoke the `payment` edge function. Throws an Error with the server-provided
// message on failure (same contract as lib/workflow.js `transition`).
async function invokePayment(body) {{
  const {{ data, error }} = await supabaseClient.functions.invoke('payment', {{ body }});
  if (error) {{
    let payload = error.context;
    if (typeof payload === 'string') {{
      try {{ payload = JSON.parse(payload); }} catch {{ payload = null; }}
    }}
    throw new Error(payload?.error || error.message || 'Payment request failed');
  }}
  if (data?.ok === false) throw new Error(data.error || 'Payment request failed');
  return data;
}}

// Create (or reuse) a payment intent for the record.
// Returns {{ reference, amount, currency, status }}.
export function createPaymentIntent(id) {{
  return invokePayment({{ action: 'create_intent', id }});
}}

// Confirm the payment. `card` is {{ number, exp_month, exp_year, cvc }}.
// The dev simulator declines Stripe's test card 4000000000000002.
export function confirmPayment(id, card) {{
  return invokePayment({{ action: 'confirm', id, card }});
}}

// Current payment status for the record: {{ status, reference }}.
export function getPaymentStatus(id) {{
  return invokePayment({{ action: 'status', id }});
}}
"""
