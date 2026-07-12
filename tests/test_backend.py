"""
Backend Integration Test for App App Generation

This test generates a complete app application backend and sets up the database.
"""

import pytest
import os
import sys
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch
import psycopg2
from dotenv import load_dotenv, dotenv_values
from unibizkit.cli import CLI
from conftest import HAS_SECONDARY_MODEL, PRIMARY_BASE, assert_secondary_model_is_normal_app


def _run(cmd, timeout=600):
    """Run a command, capture output, print it in order, and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    return result


def _http_json(method, url, *, headers=None, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def _api_env():
    # Tests reach Supabase (Kong) directly via backend/.env, not the Vite proxy.
    values = dotenv_values(Path("test-app/backend/.env"))
    api_url = values.get("SUPABASE_URL")
    anon_key = values.get("SUPABASE_ANON_KEY")
    assert api_url and anon_key, "SUPABASE_URL / SUPABASE_ANON_KEY must be present in backend/.env"
    return api_url, anon_key


def _seed_user_password(email):
    security_path = Path("test-app/security_extended.json")
    assert security_path.exists(), "security_extended.json must exist. Run backend generation first."
    security = json.loads(security_path.read_text(encoding="utf-8"))
    for user in security["users"]:
        if user["email"] == email:
            return user["password"]
    raise AssertionError(f"Seed user not found: {email}")


def _login(api_url, anon_key, email):
    status, body = _http_json(
        "POST",
        f"{api_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        body={"email": email, "password": _seed_user_password(email)},
    )
    assert status == 200, f"Login failed for {email}: {status} {body}"
    assert body["access_token"]
    return body["access_token"]


def _call_edge_function_script(email, function_name, payload=None):
    script = Path("test-app/bin/dev-supabase-call-edge-function.py")
    assert script.exists(), "dev-supabase-call-edge-function.py must be generated"
    args = [
        sys.executable,
        str(script),
        email,
        function_name,
    ]
    if payload is not None:
        args.append(json.dumps(payload))
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    assert result.stdout, "Edge function caller should print a JSON response"
    return result.returncode, json.loads(result.stdout)


def _wait_for_order_values(api_url, anon_key, token, order_id, expected, timeout=5):
    encoded_filter = urllib.parse.urlencode({
        "id": f"eq.{order_id}",
        "select": ",".join(expected.keys()),
    })
    deadline = time.monotonic() + timeout
    last_rows = None
    time.sleep(0.1)
    while time.monotonic() < deadline:
        status, rows = _http_json(
            "GET",
            f"{api_url}/rest/v1/order?{encoded_filter}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
        )
        assert status == 200
        last_rows = rows
        if rows and len(rows) == 1 and all(rows[0].get(key) == value for key, value in expected.items()):
            return rows
        time.sleep(0.1)
    raise AssertionError(f"Expected order values {expected}, got {last_rows}")


def test_ubk_dev_model_is_normal_app():
    if not HAS_SECONDARY_MODEL:
        pytest.skip("UBK_DEV_MODEL is not set; secondary dev environment disabled")
    assert_secondary_model_is_normal_app()


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
        with patch('sys.argv', [
            'uni-biz-kit', 'models/test-app',
            '--output-dir', str(output_dir),
            '--dev-base-port', str(PRIMARY_BASE),
        ]):
            cli.run()

        assert output_dir.exists()

        backend_dir = output_dir / 'backend'
        original_cwd = os.getcwd()

        try:
            print("Running dev-supabase-start.py...")
            create_script = output_dir / 'bin' / 'dev-supabase-start.py'
            result = _run([sys.executable, str(create_script)], timeout=600)
            assert result.returncode == 0, f"dev-supabase-start.py failed with code {result.returncode}"

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
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_secondary_backend_postgres_responds(self):
        """Smoke-test the second dev environment's Supabase (UBK_DEV_MODEL).

        Generates the secondary model on the +50 port offset, brings up its own
        Supabase stack, resets its schema/seed data, then connects to its Postgres
        and verifies the generated schema is present — i.e. the second environment's
        database is live and independent from the primary one. Kept model-agnostic
        so it works with any UBK_DEV_MODEL.
        """
        from conftest import generate_secondary_model, SECONDARY_MODEL

        output_dir = generate_secondary_model()
        backend_dir = output_dir / "backend"

        # dev-supabase-start.py self-fronts a temporary /api proxy on a cold start,
        # so no frontend dev server is needed here.
        print(f"Running dev-supabase-start.py for {SECONDARY_MODEL}...")
        create_script = output_dir / "bin" / "dev-supabase-start.py"
        result = _run([sys.executable, str(create_script)], timeout=600)
        assert result.returncode == 0, f"dev-supabase-start.py failed with code {result.returncode}"

        print(f"Running dev-supabase-reset-schema-and-data.py for {SECONDARY_MODEL}...")
        reset_script = output_dir / "bin" / "dev-supabase-reset-schema-and-data.py"
        result = _run([sys.executable, str(reset_script), "--force"], timeout=120)
        assert result.returncode == 0, f"dev-supabase-reset-schema-and-data.py failed with code {result.returncode}"

        # Read straight from the dummy .env file (do not pollute os.environ, so the
        # primary tests that follow still resolve their own DB_URL).
        db_url = dotenv_values(backend_dir / ".env").get("DB_URL")
        assert db_url, f"DB_URL must be present in {SECONDARY_MODEL}/backend/.env"

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
                )
                (table_count,) = cur.fetchone()
                assert table_count > 0, (
                    f"{SECONDARY_MODEL} backend has no tables in the public schema"
                )
        finally:
            conn.close()

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_order_shipping_costs_rule_via_supabase_api(self):
        """Run the FEEL shipping rule through PostgREST + Edge Function APIs."""
        api_url, anon_key = _api_env()
        user1_token = _login(api_url, anon_key, "user1@test.com")

        user1_headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {user1_token}",
            "Content-Type": "application/json",
        }
        status, created = _http_json(
            "POST",
            f"{api_url}/rest/v1/order",
            headers={**user1_headers, "Prefer": "return=representation"},
            body={
                "order_date": "2026-05-09T12:00:00Z",
                "shipping_address_street": "Shipping rule test street",
                "shipping_address_city": "Bilbao",
                "shipping_address_province": "Bizkaia",
                "shipping_address_country": "Spain",
            },
        )
        assert status == 201, f"Order creation failed: {status} {created}"
        assert len(created) == 1
        order_id = created[0]["id"]

        _wait_for_order_values(
            api_url,
            anon_key,
            user1_token,
            order_id,
            {"shipping_costs": 6, "total_amount": 0},
        )

        product_filter = urllib.parse.urlencode({
            "sku": "eq.product_sku_1",
            "select": "id",
        })
        status, products = _http_json(
            "GET",
            f"{api_url}/rest/v1/product?{product_filter}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {user1_token}"},
        )
        assert status == 200
        assert len(products) == 1
        product_id = products[0]["id"]

        status, created_items = _http_json(
            "POST",
            f"{api_url}/rest/v1/order_item",
            headers={**user1_headers, "Prefer": "return=representation"},
            body={
                "order": order_id,
                "product": product_id,
                "quantity": 10,
            },
        )
        assert status == 201, f"Order item creation failed: {status} {created_items}"

        _wait_for_order_values(
            api_url,
            anon_key,
            user1_token,
            order_id,
            {"shipping_costs": 0, "total_amount": 100.1},
        )

        direct_status, direct_body = _http_json(
            "PATCH",
            f"{api_url}/rest/v1/order?id=eq.{order_id}",
            headers={**user1_headers, "Prefer": "return=representation"},
            body={"state": "ordered"},
        )
        assert direct_status >= 400
        assert "workflow-transition" in json.dumps(direct_body)

        returncode, auth_rule_result = _call_edge_function_script(
            "user1@test.com",
            "current-customer-email",
        )
        assert returncode == 0, f"Auth rule execution failed for user1: {auth_rule_result}"
        assert auth_rule_result["status"] == 200
        assert auth_rule_result["body"] == {"data": "user1@test.com"}

        returncode, transition_result = _call_edge_function_script(
            "user1@test.com",
            "workflow-transition",
            {
                "concept": "order",
                "id": order_id,
                "to_state": "ordered",
                "comment": "Order confirmed from test",
            },
        )
        assert returncode == 0, f"Workflow transition failed for user1: {transition_result}"
        assert transition_result["status"] == 200
        transition_body = transition_result["body"]
        assert transition_body["rules"] == [
            "order-shipping-costs",
            "order-save-ordered-total-amount",
        ]
        assert transition_body["data"]["state"] == "ordered"
        assert transition_body["data"]["ordered_total_amount"] == 100.1
        assert transition_body["data"]["state_info"]["last_transition"]["comment"] == "Order confirmed from test"

        load_dotenv(Path('test-app/backend/.env'))
        db_url = os.getenv("DB_URL")
        assert db_url, "DB_URL must be present in test-app/backend/.env"
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE "order" SET "ordered_total_amount" = %s WHERE "id" = %s;',
                    (0, order_id),
                )
            conn.commit()
        finally:
            conn.close()

        returncode, accepted_result = _call_edge_function_script(
            "admin@test.com",
            "workflow-transition",
            {
                "concept": "order",
                "id": order_id,
                "to_state": "accepted",
                "comment": "Try to accept changed order",
            },
        )
        assert returncode == 0
        assert accepted_result["status"] == 200
        assert accepted_result["body"] == {
            "ok": False,
            "error": "Order total has changed since it was ordered",
            "rule": "order-check-ordered-total-amount",
        }

        returncode, user2_result = _call_edge_function_script(
            "user2@test.com",
            "order-shipping-costs",
            {"id": order_id},
        )
        assert returncode != 0
        assert user2_result["status"] == 403
        assert user2_result["body"] == {
            "error": "Expected exactly one accessible record",
            "count": 0,
        }

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_workflow_transition_rejects_invalid_prefill_validation(self):
        """workflow-transition must reject invalid CSV-derived prefill field combinations."""
        api_url, anon_key = _api_env()
        user1_token = _login(api_url, anon_key, "user1@test.com")

        user1_headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {user1_token}",
            "Content-Type": "application/json",
        }
        status, created = _http_json(
            "POST",
            f"{api_url}/rest/v1/order",
            headers={**user1_headers, "Prefer": "return=representation"},
            body={
                "order_date": "2026-05-10T12:00:00Z",
                "shipping_address_street": "Invalid province test street",
                "shipping_address_country": "Spain",
                "shipping_address_province": "xxx",
                "shipping_address_city": "Bilbao",
            },
        )
        assert status == 201, f"Order creation failed: {status} {created}"
        order_id = created[0]["id"]

        returncode, transition_result = _call_edge_function_script(
            "user1@test.com",
            "workflow-transition",
            {
                "concept": "order",
                "id": order_id,
                "to_state": "ordered",
                "comment": "Invalid prefill validation should block",
            },
        )
        assert returncode == 0
        assert transition_result["status"] == 200
        assert transition_result["body"]["ok"] is False
        assert transition_result["body"]["error"] == (
            "Validation failed for address-shipping_address: "
            "shipping address country, shipping address province, shipping address city"
        )
        assert transition_result["body"]["validation"] == "address-shipping_address"

        encoded_filter = urllib.parse.urlencode({
            "id": f"eq.{order_id}",
            "select": "state",
        })
        status, rows = _http_json(
            "GET",
            f"{api_url}/rest/v1/order?{encoded_filter}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {user1_token}"},
        )
        assert status == 200
        assert rows == [{"state": "initial"}]

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_copy_and_rollup_triggers(self):
        """Verify copy(product,price,on_change_in_state_initial) and rollup(sum,order_item,total_price) triggers.

        Flow:
        1. Insert order in 'ordered' state (skips on_change_in_state_initial copy on creation).
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

                # Insert order in 'ordered' state so the on_change_in_state_initial copy does not fire yet.
                cur.execute(
                    'INSERT INTO "order" ("customer", "order_date", "shipping_address_street", '
                    '"shipping_address_city", "shipping_address_province", "shipping_address_country", "state") '
                    "VALUES (%s, NOW(), 'Test Street 1', 'Bilbao', 'Bizkaia', 'Spain', 'ordered') RETURNING id;",
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
                    assert up is None, f"unit_price should be NULL before on_change_in_state_initial, got {up}"

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
    def test_relation_snapshots_deleted_record_before_fk_is_set_null(self):
        load_dotenv(Path('test-app/backend/.env'))
        db_url = os.getenv("DB_URL")
        assert db_url, "DB_URL must be present in test-app/backend/.env"

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT "id" FROM "customer" LIMIT 1;')
                customer_id = cur.fetchone()[0]
                cur.execute(
                    '''INSERT INTO "product" ("name", "sku", "price")
                       VALUES ('Snapshot product', 'SNAPSHOT-DELETE-001', 12.50)
                       RETURNING id, id_presentation, name, sku;'''
                )
                product_id, id_presentation, product_name, sku = cur.fetchone()
                cur.execute(
                    '''INSERT INTO "order" (
                           "customer", "order_date", "shipping_address_street",
                           "shipping_address_city", "shipping_address_province",
                           "shipping_address_country", "state"
                       ) VALUES (%s, NOW(), 'Test Street 1', 'Bilbao', 'Bizkaia', 'Spain', 'initial')
                       RETURNING id;''',
                    (customer_id,),
                )
                order_id = cur.fetchone()[0]
                cur.execute(
                    'INSERT INTO "order_item" ("order", "product", "quantity") VALUES (%s, %s, 1) RETURNING id;',
                    (order_id, product_id),
                )
                item_id = cur.fetchone()[0]

                cur.execute('DELETE FROM "product" WHERE "id" = %s;', (product_id,))
                cur.execute(
                    'SELECT "product", "_product_deleted_snapshot" FROM "order_item" WHERE "id" = %s;',
                    (item_id,),
                )
                fk_value, snapshot = cur.fetchone()

                assert fk_value is None
                assert snapshot["id"] == product_id
                assert snapshot["id_presentation"] == id_presentation
                assert snapshot["name"] == product_name
                assert snapshot["sku"] == sku

            conn.rollback()
        finally:
            conn.close()

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    def test_copy_unit_price_on_change_in_state_initial(self):
        """copy(product,price,on_change_in_state_initial) on order_item.unit_price.

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
                        'INSERT INTO "order" ("customer","order_date","shipping_address_street",'
                        '"shipping_address_city","shipping_address_province","shipping_address_country","state") '
                        "VALUES (%s,NOW(),'Test','Bilbao','Bizkaia','Spain',%s) RETURNING id;",
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
                    'INSERT INTO "order" ("customer","order_date","shipping_address_street",'
                    '"shipping_address_city","shipping_address_province","shipping_address_country") '
                    "VALUES (%s,NOW(),'Security Test','Bilbao','Bizkaia','Spain') RETURNING id,customer;",
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
