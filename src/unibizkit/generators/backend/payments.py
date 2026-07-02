import json

from .context import Context

# Deno/TypeScript body of the `payment` edge function. The __CONFIG__ constants
# are prepended by generate_payment_function; the flow mirrors the other edge
# functions: the caller's own client reads the record (so RLS decides who can
# pay what) and the service client writes the payment fields, which are
# read-only for regular roles.
_PAYMENT_TS_BODY = """
Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) {
    return jsonResponse({ error: "Missing bearer token" }, 401);
  }

  const { action, id, card = null } = await req.json().catch(() => ({}));
  if (!action || id === undefined || id === null || id === "") {
    return jsonResponse({ error: "Missing action or id" }, 400);
  }

  const supabaseUrl = requiredEnv("SUPABASE_URL");
  const anonKey = requiredEnv("SUPABASE_ANON_KEY");
  const serviceRoleKey = requiredEnv("SUPABASE_SERVICE_ROLE_KEY");
  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authorization } },
  });
  const serviceClient = createClient(supabaseUrl, serviceRoleKey);

  const { data: authData, error: authError } = await userClient.auth.getUser();
  if (authError || !authData.user) {
    return jsonResponse({ error: authError?.message ?? "Missing authenticated user" }, 401);
  }

  const { data: rows, error: selectError } = await userClient
    .from(CONCEPT)
    .select("*")
    .eq("id", id)
    .limit(2);
  if (selectError) {
    return jsonResponse({ error: selectError.message }, 400);
  }
  if (!rows || rows.length !== 1) {
    return jsonResponse({ error: "Expected exactly one accessible record", count: rows?.length ?? 0 }, 403);
  }
  const record = rows[0];

  if (action === "status") {
    return jsonResponse({
      status: record[STATUS_FIELD] ?? "unpaid",
      reference: record[REFERENCE_FIELD] ?? null,
    });
  }

  if (action === "create_intent") {
    if (record[STATUS_FIELD] === "paid") {
      return jsonResponse({ ok: false, error: "Record is already paid" });
    }
    const amount = Number(record[AMOUNT_FIELD]);
    if (!Number.isFinite(amount) || amount <= 0) {
      return jsonResponse({ ok: false, error: `No chargeable amount in ${AMOUNT_FIELD}` });
    }

    let reference: string;
    if (DEV_MODE) {
      reference = `pi_dev_${crypto.randomUUID().replaceAll("-", "").slice(0, 24)}`;
    } else {
      const intent = await stripeRequest("/v1/payment_intents", {
        amount: String(Math.round(amount * 100)),
        currency: CURRENCY,
        "metadata[concept]": CONCEPT,
        "metadata[record_id]": String(id),
      });
      if (intent.error) {
        return jsonResponse({ ok: false, error: intent.error.message ?? "Stripe error" });
      }
      reference = intent.id;
    }

    const writeError = await writePayment(serviceClient, id, {
      [STATUS_FIELD]: "pending",
      [REFERENCE_FIELD]: reference,
    });
    if (writeError) {
      return jsonResponse({ error: writeError }, 400);
    }
    return jsonResponse({ reference, amount, currency: CURRENCY, status: "pending" });
  }

  if (action === "confirm") {
    const reference = record[REFERENCE_FIELD];
    if (!reference || record[STATUS_FIELD] !== "pending") {
      return jsonResponse({ ok: false, error: "No pending payment for this record; create an intent first" });
    }

    let status: string;
    let failureMessage: string | null = null;
    if (DEV_MODE) {
      // Simulator: mimic Stripe's declined test card; any other plausible card succeeds.
      const cardNumber = String(card?.number ?? "").replaceAll(" ", "");
      if (cardNumber === "4000000000000002") {
        status = "failed";
        failureMessage = "Your card was declined (simulated)";
      } else if (cardNumber.length < 12) {
        status = "failed";
        failureMessage = "Invalid card number (simulated)";
      } else {
        status = "paid";
      }
    } else {
      const confirmed = await stripeRequest(`/v1/payment_intents/${reference}/confirm`, {
        payment_method: String(card?.payment_method ?? ""),
      });
      if (confirmed.error) {
        status = "failed";
        failureMessage = confirmed.error.message ?? "Stripe error";
      } else {
        status = confirmed.status === "succeeded" ? "paid" : "failed";
      }
    }

    const writeError = await writePayment(serviceClient, id, { [STATUS_FIELD]: status });
    if (writeError) {
      return jsonResponse({ error: writeError }, 400);
    }
    if (status !== "paid") {
      return jsonResponse({ ok: false, error: failureMessage ?? "Payment failed", status });
    }
    return jsonResponse({ status, reference });
  }

  return jsonResponse({ error: `Unknown action ${action}` }, 400);
});

async function stripeRequest(path: string, form: Record<string, string>) {
  const secretKey = requiredEnv("STRIPE_SECRET_KEY");
  const response = await fetch(`https://api.stripe.com${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secretKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams(form),
  });
  return await response.json();
}

async function writePayment(
  serviceClient: ReturnType<typeof createClient>,
  id: unknown,
  fields: Record<string, unknown>,
): Promise<string | null> {
  const { data: updatedRows, error } = await serviceClient
    .from(CONCEPT)
    .update(fields)
    .eq("id", id)
    .select("id")
    .limit(2);
  if (error) {
    return error.message;
  }
  if (!updatedRows || updatedRows.length !== 1) {
    return "Expected exactly one updated record";
  }
  return null;
}

function requiredEnv(name: string): string {
  const value = Deno.env.get(name);
  if (!value) {
    throw new Error(`Missing environment variable ${name}`);
  }
  return value;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
"""


def generate_payment_function(ctx: Context) -> dict[str, dict[str, str]]:
    """Generate the `payment` edge function when system.payments is configured."""
    payments = ctx.system_config.get("payments")
    if not payments:
        return {}

    header = (
        'import { createClient } from "@supabase/supabase-js";\n'
        "\n"
        f"const DEV_MODE = {json.dumps(payments['dev_mode'])};\n"
        f"const CONCEPT = {json.dumps(payments['concept'])};\n"
        f"const AMOUNT_FIELD = {json.dumps(payments['amount_field'])};\n"
        f"const STATUS_FIELD = {json.dumps(payments['status_field'])};\n"
        f"const REFERENCE_FIELD = {json.dumps(payments['reference_field'])};\n"
        f"const CURRENCY = {json.dumps(payments['currency'])};\n"
    )
    deno_json = json.dumps({
        "imports": {
            "@supabase/supabase-js": "npm:@supabase/supabase-js@2.89.0",
        }
    }, indent=2) + "\n"
    return {
        "payment": {
            "index.ts": header + _PAYMENT_TS_BODY,
            "deno.json": deno_json,
        }
    }
