"""
Backend Integration Test for App App Generation

This test generates a complete app application backend and sets up the database.
"""

import pytest
import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch
import psycopg2
from dotenv import load_dotenv
from unibizkit.cli import CLI


def _run(cmd, timeout=600):
    """Run a command, capture output, print it in order, and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    return result


class TestAppBackend:
    """Backend integration tests for app app generation."""

    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_generate_app_backend_and_setup_database(self):
        """Test generating a complete app app backend and setting up the database.

        This integration test:
        1. Generates a complete app application from schema
        2. Sets up Supabase database with schema and development seed data
        3. Verifies the database setup is successful

        Note: This test may take several minutes to run.
        """
        cli = CLI()

        # Use the app schema from models
        output_dir = Path('test-app').resolve()

        print("Executing uni-biz-kit: generating a complete app application from schema")
        with patch('sys.argv', ['uni-biz-kit', 'models/test-app', '--output-dir', str(output_dir)]):
            cli.run()

        assert output_dir.exists()

        backend_dir = output_dir / 'backend'
        original_cwd = os.getcwd()

        try:
            supabase_dir = backend_dir / 'supabase'
            if not supabase_dir.exists():
                print("Running dev-supabase-start.py...")
                create_script = output_dir / 'bin' / 'dev-supabase-start.py'
                result = _run([sys.executable, str(create_script)], timeout=600)
                assert result.returncode == 0, f"dev-supabase-start.py failed with code {result.returncode}"
            else:
                print("Supabase directory already exists, skipping initialization")

            print("Running dev-supabase-reset-schema-and-data.py...")
            reset_script = output_dir / 'bin' / 'dev-supabase-reset-schema-and-data.py'
            result = _run([sys.executable, str(reset_script), '--force'], timeout=120)
            assert result.returncode == 0, f"dev-supabase-reset-schema-and-data.py failed with code {result.returncode}"

            load_dotenv(backend_dir / '.env')
            db_url = os.getenv("DB_URL")
            assert db_url, "DB_URL must be present in test-app/backend/.env"

            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT p.name, c.name
                        FROM "product" p
                        JOIN "category_product" cp ON cp.product_id = p.id
                        JOIN "category" c ON c.id = cp.category_id
                        WHERE p.sku = 'SEED-KBD-001'
                          AND c.slug = 'seeded-accessories';
                    """)
                    assert cur.fetchone() == ('Seeded Keyboard', 'Seeded Accessories')
            finally:
                conn.close()

        finally:
            os.chdir(original_cwd)

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_copy_and_rollup_triggers(self):
        """Verify copy(product,price,state_initial) and rollup(sum,order_item,total_price) triggers.

        Flow:
        1. Insert order in 'ordered' state (skips state_initial copy on creation).
        2. Insert two order_items referencing the seeded product — unit_price stays NULL.
        3. Transition order to 'initial' — copy trigger sets unit_price from product.price.
        4. Verify total_amount rollup reflects the copied prices.
        """
        load_dotenv(Path('test-app/backend/.env'))
        db_url = os.getenv("DB_URL")
        assert db_url, "DB_URL must be present in test-app/backend/.env"

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT "id" FROM "customer" LIMIT 1;')
                row = cur.fetchone()
                assert row, "No customer found — run the full backend test first to seed data"
                customer_id = row[0]

                cur.execute("SELECT \"id\", \"price\" FROM \"product\" WHERE \"sku\" = 'SEED-KBD-001';")
                row = cur.fetchone()
                assert row, "Seeded product not found — run the full backend test first"
                product_id, product_price = row[0], float(row[1])

                # Insert order in 'ordered' state so the state_initial copy does not fire yet.
                cur.execute(
                    'INSERT INTO "order" ("customer", "order_date", "shipping_address", "state") '
                    "VALUES (%s, NOW(), 'Test Street 1', 'ordered') RETURNING id;",
                    (customer_id,),
                )
                order_id = cur.fetchone()[0]

                # Insert items — unit_price is a copy-calculated field, starts NULL.
                cur.execute(
                    'INSERT INTO "order_item" ("order", "product", "quantity") VALUES (%s, %s, 2);',
                    (order_id, product_id),
                )
                cur.execute(
                    'INSERT INTO "order_item" ("order", "product", "quantity") VALUES (%s, %s, 3);',
                    (order_id, product_id),
                )

                cur.execute('SELECT "unit_price" FROM "order_item" WHERE "order" = %s;', (order_id,))
                for (up,) in cur.fetchall():
                    assert up is None, f"unit_price should be NULL before state_initial, got {up}"

                # Transition to 'initial' — copy trigger fires and sets unit_price.
                cur.execute('UPDATE "order" SET "state" = %s WHERE "id" = %s;', ('initial', order_id))

                cur.execute('SELECT "unit_price" FROM "order_item" WHERE "order" = %s;', (order_id,))
                for (up,) in cur.fetchall():
                    assert float(up) == product_price, (
                        f"unit_price should equal product price {product_price}, got {up}"
                    )

                # Rollup: (2 + 3) × product_price
                expected_total = round(5 * product_price, 2)
                cur.execute('SELECT "total_amount" FROM "order" WHERE "id" = %s;', (order_id,))
                total = float(cur.fetchone()[0])
                assert total == expected_total, f"Expected {expected_total}, got {total}"

            conn.rollback()
        finally:
            conn.close()

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_copy_unit_price_state_initial(self):
        """copy(product,price,state_initial) on order_item.unit_price.

        Cases:
        A. INSERT item while order.state='initial'  → unit_price = product.price
        B. INSERT item while order.state≠'initial'  → unit_price = NULL
        C. UPDATE order.state → 'initial'           → unit_price set for existing items
        D. UPDATE order.state → non-initial         → unit_price unchanged (stays NULL)
        """
        load_dotenv(Path('test-app/backend/.env'))
        db_url = os.getenv("DB_URL")
        assert db_url, "DB_URL must be present in test-app/backend/.env"

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT "id" FROM "customer" LIMIT 1;')
                (customer_id,) = cur.fetchone()

                cur.execute("SELECT \"id\", \"price\" FROM \"product\" WHERE \"sku\" = 'SEED-KBD-001';")
                product_id, product_price = cur.fetchone()
                product_price = float(product_price)

                def make_order(state):
                    cur.execute(
                        'INSERT INTO "order" ("customer","order_date","shipping_address","state") '
                        "VALUES (%s,NOW(),'Test',  %s) RETURNING id;",
                        (customer_id, state),
                    )
                    return cur.fetchone()[0]

                def add_item(order_id):
                    cur.execute(
                        'INSERT INTO "order_item" ("order","product","quantity") VALUES (%s,%s,1) RETURNING id;',
                        (order_id, product_id),
                    )
                    return cur.fetchone()[0]

                def unit_price(item_id):
                    cur.execute('SELECT "unit_price" FROM "order_item" WHERE "id" = %s;', (item_id,))
                    v = cur.fetchone()[0]
                    return float(v) if v is not None else None

                # ── Case A: INSERT while order.state = 'initial' ──────────────
                order_a = make_order('initial')
                item_a = add_item(order_a)
                assert unit_price(item_a) == product_price, (
                    f"Case A: expected {product_price}, got {unit_price(item_a)}"
                )

                # ── Case B: INSERT while order.state ≠ 'initial' ─────────────
                order_b = make_order('ordered')
                item_b = add_item(order_b)
                assert unit_price(item_b) is None, (
                    f"Case B: expected NULL, got {unit_price(item_b)}"
                )

                # ── Case C: UPDATE order.state → 'initial' ────────────────────
                cur.execute('UPDATE "order" SET "state"=%s WHERE "id"=%s;', ('initial', order_b))
                assert unit_price(item_b) == product_price, (
                    f"Case C: expected {product_price}, got {unit_price(item_b)}"
                )

                # ── Case D: UPDATE order.state → non-initial ──────────────────
                order_d = make_order('ordered')
                item_d = add_item(order_d)          # NULL (Case B scenario)
                cur.execute('UPDATE "order" SET "state"=%s WHERE "id"=%s;', ('accepted', order_d))
                assert unit_price(item_d) is None, (
                    f"Case D: expected NULL after non-initial transition, got {unit_price(item_d)}"
                )

                # ── Case E: UPDATE item.product while order.state='initial' ───
                # unit_price must be recopied from the new product.
                cur.execute(
                    "INSERT INTO \"product\" (\"name\",\"price\",\"stock_quantity\",\"sku\",\"status\")"
                    " VALUES ('Alt Product',99.00,10,'ALT-001','published') RETURNING id,price;",
                )
                alt_product_id, alt_price = cur.fetchone()
                alt_price = float(alt_price)

                order_e = make_order('initial')
                item_e = add_item(order_e)          # product_id, unit_price = product_price
                assert unit_price(item_e) == product_price, "Case E pre-condition failed"

                cur.execute(
                    'UPDATE "order_item" SET "product"=%s WHERE "id"=%s;',
                    (alt_product_id, item_e),
                )
                assert unit_price(item_e) == alt_price, (
                    f"Case E: expected {alt_price} after product change, got {unit_price(item_e)}"
                )

                # ── Case F: UPDATE item.product while order.state≠'initial' ──
                # unit_price must NOT change.
                order_f = make_order('ordered')
                item_f = add_item(order_f)          # NULL (no copy, state≠initial)
                cur.execute('UPDATE "order" SET "state"=%s WHERE "id"=%s;', ('initial', order_f))
                assert unit_price(item_f) == product_price, "Case F pre-condition failed"
                cur.execute('UPDATE "order" SET "state"=%s WHERE "id"=%s;', ('ordered', order_f))

                cur.execute(
                    'UPDATE "order_item" SET "product"=%s WHERE "id"=%s;',
                    (alt_product_id, item_f),
                )
                assert unit_price(item_f) == product_price, (
                    f"Case F: unit_price should be unchanged when order.state≠initial, got {unit_price(item_f)}"
                )

            conn.rollback()
        finally:
            conn.close()

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_copy_logged_on_insert_security(self):
        """copy_logged_on_insert must always override the user-provided value on INSERT.

        In a direct DB connection auth.uid() is NULL, so the field must always be
        set to NULL regardless of what the caller sends — the user must never be able
        to inject an arbitrary FK value.
        Direct UPDATE of the field must also be blocked.
        """
        load_dotenv(Path('test-app/backend/.env'))
        db_url = os.getenv("DB_URL")
        assert db_url, "DB_URL must be present in test-app/backend/.env"

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT "id" FROM "customer" LIMIT 1;')
                (customer_id,) = cur.fetchone()

                # INSERT with an explicit customer value — trigger must override it.
                cur.execute(
                    'INSERT INTO "order" ("customer","order_date","shipping_address") '
                    "VALUES (%s,NOW(),'Security Test') RETURNING id,customer;",
                    (customer_id,),
                )
                order_id, actual_customer = cur.fetchone()
                assert actual_customer is None, (
                    f"INSERT: user-provided customer {customer_id} was not overridden — "
                    f"got {actual_customer}"
                )

                # Direct UPDATE must also be blocked.
                cur.execute(
                    'UPDATE "order" SET "customer"=%s WHERE "id"=%s;',
                    (customer_id, order_id),
                )
                cur.execute('SELECT "customer" FROM "order" WHERE "id"=%s;', (order_id,))
                assert cur.fetchone()[0] is None, (
                    "UPDATE: customer must not be changeable by a direct write"
                )

            conn.rollback()
        finally:
            conn.close()
