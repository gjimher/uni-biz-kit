"""
Payment capability tests (system.payments → 'payment' edge function).

Generation checks verify the edge function and the frontend lib are emitted.
Integration tests exercise the dev-mode simulator end to end against the local
Supabase: create_intent → confirm (paid / declined) and the write protection of
the payment fields.

Requires the test-app backend deployed (run tests/test_backend.py first).
"""

import os
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

from test_workflow import _call_edge_function_script

# Stripe's classic test cards, honored by the dev simulator.
CARD_OK = {"number": "4242424242424242", "exp_month": 12, "exp_year": 2030, "cvc": "123"}
CARD_DECLINED = {"number": "4000000000000002", "exp_month": 12, "exp_year": 2030, "cvc": "123"}


def test_payment_edge_function_generated():
    index_ts = Path("test-app/backend/supabase/functions/payment/index.ts")
    assert index_ts.exists(), "payment edge function must be generated (run tests/test_backend.py first)"
    content = index_ts.read_text()
    assert "const DEV_MODE = true;" in content
    assert 'const AMOUNT_FIELD = "total_amount";' in content
    assert 'const STATUS_FIELD = "payment_status";' in content
    assert "4000000000000002" in content, "dev simulator must decline Stripe's test card"
    assert "api.stripe.com" in content, "non-dev mode must proxy to the Stripe API"


def test_payment_frontend_lib_generated():
    lib = Path("test-app/frontend/src/presentation/lib/payment.js")
    assert lib.exists(), "payment lib must be generated (run tests/test_frontend.py first)"
    content = lib.read_text()
    assert "export const paymentsEnabled = true;" in content
    assert "export const paymentsDevMode = true;" in content
    assert "functions.invoke('payment'" in content


def _connect():
    env_path = Path("test-app/backend/.env")
    if not env_path.exists():
        pytest.skip("test-app/backend/.env not found. Run generate first.")
    load_dotenv(env_path)
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found in .env")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    return conn


def _create_order_with_item_as_user1(cur):
    """Create an order (state initial) with one item as user1, so RLS lets
    user1 read it in the payment edge function and total_amount is > 0."""
    cur.execute("SELECT id FROM auth.users WHERE email = 'user1@test.com'")
    row = cur.fetchone()
    if not row:
        pytest.skip("user1@test.com not found in auth.users — run tests/test_backend.py first")
    user1_id = row[0]

    cur.execute("SELECT \"id\" FROM \"product\" WHERE \"sku\" = 'SEED-KBD-001';")
    row = cur.fetchone()
    assert row, "Seeded product not found — run tests/test_backend.py first"
    product_id = row[0]

    cur.execute("BEGIN;")
    cur.execute("SET LOCAL ROLE authenticated")
    cur.execute(
        "SELECT set_config('request.jwt.claims', "
        f"'{{\"sub\": \"{user1_id}\", \"role\": \"authenticated\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}', true)"
    )
    cur.execute(
        'INSERT INTO "order" ("order_date", "shipping_address_street", "shipping_address_city", '
        '"shipping_address_province", "shipping_address_country", "state") '
        "VALUES (NOW(), 'Payment Test St 1', 'Bilbao', 'Bizkaia', 'Spain', 'initial') RETURNING id;"
    )
    order_id = cur.fetchone()[0]
    # unit_price is copied from product.price on insert (state initial); the
    # rollup then sets order.total_amount.
    cur.execute(
        'INSERT INTO "order_item" ("order", "product", "quantity") VALUES (%s, %s, 2);',
        (order_id, product_id),
    )
    cur.execute("COMMIT;")

    cur.execute('SELECT "total_amount" FROM "order" WHERE "id" = %s;', (order_id,))
    total = float(cur.fetchone()[0])
    assert total > 0, "Order total_amount must be > 0 for the payment tests"
    return order_id


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_payment_dev_flow_paid():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            order_id = _create_order_with_item_as_user1(cur)

            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "create_intent", "id": order_id}
            )
            assert code == 0 and res["status"] == 200, res
            assert res["body"]["status"] == "pending"
            reference = res["body"]["reference"]
            assert reference.startswith("pi_dev_"), reference

            cur.execute('SELECT "payment_status", "payment_reference" FROM "order" WHERE "id" = %s;', (order_id,))
            status, db_reference = cur.fetchone()
            assert status == "pending" and db_reference == reference

            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "confirm", "id": order_id, "card": CARD_OK}
            )
            assert code == 0 and res["status"] == 200, res
            assert res["body"]["status"] == "paid"

            cur.execute('SELECT "payment_status" FROM "order" WHERE "id" = %s;', (order_id,))
            assert cur.fetchone()[0] == "paid"

            # A paid record cannot get a new intent.
            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "create_intent", "id": order_id}
            )
            assert res["body"]["ok"] is False, res

            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "status", "id": order_id}
            )
            assert res["status"] == 200 and res["body"]["status"] == "paid", res
    finally:
        conn.close()


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_payment_dev_flow_declined_card():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            order_id = _create_order_with_item_as_user1(cur)

            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "create_intent", "id": order_id}
            )
            assert code == 0 and res["status"] == 200, res

            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "confirm", "id": order_id, "card": CARD_DECLINED}
            )
            assert res["body"]["ok"] is False, res
            assert res["body"]["status"] == "failed"

            cur.execute('SELECT "payment_status" FROM "order" WHERE "id" = %s;', (order_id,))
            assert cur.fetchone()[0] == "failed"

            # Confirm requires a pending intent: a failed payment needs a new intent first.
            code, res = _call_edge_function_script(
                "user1@test.com", "payment", {"action": "confirm", "id": order_id, "card": CARD_OK}
            )
            assert res["body"]["ok"] is False, res
    finally:
        conn.close()


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_payment_fields_protected_from_client_writes():
    """payment_status is by_rules: only the edge function (service role) may write it."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            order_id = _create_order_with_item_as_user1(cur)

            cur.execute("SELECT id FROM auth.users WHERE email = 'user1@test.com'")
            user1_id = cur.fetchone()[0]

            cur.execute("BEGIN;")
            cur.execute("SET LOCAL ROLE authenticated")
            cur.execute(
                "SELECT set_config('request.jwt.claims', "
                f"'{{\"sub\": \"{user1_id}\", \"role\": \"authenticated\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}', true)"
            )
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute('UPDATE "order" SET "payment_status" = %s WHERE "id" = %s;', ("paid", order_id))
            cur.execute("ROLLBACK;")
    finally:
        conn.close()
