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
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import psycopg2
from dotenv import load_dotenv, dotenv_values
from conftest import (
    HAS_SECONDARY_MODEL, assert_secondary_model_is_normal_app, dev_base_port,
)
from edge_function import call_edge_function as _call_edge_function_script


def _run(cmd, timeout=600, input=None):
    """Run a command, capture output, print it in order, and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
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
    def test_generate_app_backend_and_setup_database(self, request, generated_test_app):
        """Test generating a complete app app backend and setting up the database.

        This integration test:
        1. Generates a complete app application from schema
        2. Sets up Supabase database with schema and development seed data
        3. Verifies the database setup is successful

        Note: This test may take several minutes to run.
        """
        output_dir = generated_test_app
        base_port = dev_base_port(output_dir)

        backend_dir = output_dir / 'backend'
        original_cwd = os.getcwd()

        try:
            print("Running dev-supabase-start.py...")
            create_script = output_dir / 'bin' / 'dev-supabase-start.py'
            result = _run([sys.executable, str(create_script)], timeout=600)
            assert result.returncode == 0, f"dev-supabase-start.py failed with code {result.returncode}"

            print("Setting a local Edge Function secret...")
            set_secret_script = output_dir / 'bin' / 'dev-set-secret.py'
            result = _run(
                [sys.executable, str(set_secret_script), 'UBK_TEST_SECRET', '--stdin'],
                timeout=600,
                input='dev-secret-value\n',
            )
            assert result.returncode == 0, f"dev-set-secret.py failed with code {result.returncode}"
            assert 'dev-secret-value' not in result.stdout
            secrets_file = backend_dir / '.env.secrets'
            functions_env = backend_dir / 'supabase' / 'functions' / '.env'
            generated_functions_env = backend_dir / 'supabase' / 'functions' / '.env.generated'
            assert secrets_file.stat().st_mode & 0o777 == 0o600
            assert 'UBK_TEST_SECRET=dev-secret-value\n' in secrets_file.read_text()
            effective_env = functions_env.read_text()
            assert generated_functions_env.read_text() == (
                'INTEGRATION_SCHEDULER_TOKEN=dev-integration-scheduler-token\n'
                f'UBK_DEV_BASE_PORT={base_port}\n'
            )
            assert f'UBK_DEV_BASE_PORT={base_port}\n' in effective_env
            assert 'UBK_TEST_SECRET=dev-secret-value\n' in effective_env
            with open(backend_dir / 'supabase' / 'config.toml', 'rb') as config_file:
                project_id = tomllib.load(config_file)['project_id']
            inspected = _run([
                'docker', 'inspect', f'supabase_edge_runtime_{project_id}', '--format',
                '{{range .Config.Env}}{{if eq . "UBK_TEST_SECRET=dev-secret-value"}}found{{end}}{{end}}',
            ])
            assert inspected.returncode == 0
            assert inspected.stdout.strip() == 'found'
            base_port_inspected = _run([
                'docker', 'inspect', f'supabase_edge_runtime_{project_id}', '--format',
                '{{range .Config.Env}}{{if eq . "UBK_DEV_BASE_PORT=' + str(base_port) + '"}}found{{end}}{{end}}',
            ])
            assert base_port_inspected.returncode == 0
            assert base_port_inspected.stdout.strip() == 'found'

            unchanged = _run(
                [sys.executable, str(set_secret_script), 'UBK_TEST_SECRET', '--stdin'],
                timeout=600,
                input='dev-secret-value\n',
            )
            assert unchanged.returncode == 0
            assert 'dev-secret-value' not in unchanged.stdout
            assert 'Nothing to do.' in unchanged.stdout

            if request.config.getoption("--slow"):
                def container_identity(name):
                    state = _run([
                        'docker', 'inspect', name, '--format', '{{.Id}} {{.State.StartedAt}}',
                    ])
                    assert state.returncode == 0
                    return tuple(state.stdout.strip().split())

                db_container = f'supabase_db_{project_id}'
                edge_container = f'supabase_edge_runtime_{project_id}'
                db_before = container_identity(db_container)
                edge_before = container_identity(edge_container)
                function_js = backend_dir / 'supabase' / 'functions' / 'external-company-dummy-ok' / 'function.js'
                original_function_js = function_js.read_text()
                function_js.write_text(original_function_js + '\n// selective Edge Runtime restart probe\n')
                try:
                    code_change = _run([sys.executable, str(create_script)], timeout=60)
                    assert code_change.returncode == 0
                    assert 'Only JS/TS Edge Function code changed' in code_change.stdout
                    assert 'Edge Runtime restarted with updated JS/TS functions.' in code_change.stdout
                    assert container_identity(db_container) == db_before
                    edge_after = container_identity(edge_container)
                    assert edge_after[0] == edge_before[0]
                    assert edge_after[1] != edge_before[1]
                finally:
                    function_js.write_text(original_function_js)
                    restored = _run([sys.executable, str(create_script)], timeout=60)
                    assert restored.returncode == 0
                    assert 'Edge Runtime restarted with updated JS/TS functions.' in restored.stdout

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
    def test_dev_deploy_data_restores_and_updates_categories(self):
        """The generated command reapplies deleted and modified deployed rows."""
        db_url = dotenv_values(Path("test-app/backend/.env")).get("DB_URL")
        assert db_url
        conn = psycopg2.connect(db_url)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM category WHERE name = 'Deployed Hardware'")
                cur.execute(
                    "UPDATE category SET description = 'locally changed' "
                    "WHERE name = 'Deployed Services'"
                )
                cur.execute(
                    "INSERT INTO _integration(name, on_removed) "
                    "VALUES ('removed-from-model', '\"ignore\"'::jsonb) "
                    "ON CONFLICT (name) DO NOTHING"
                )
        finally:
            conn.close()

        result = _run([
            sys.executable,
            "test-app/bin/dev-deploy-data.py",
            "models/test-app/deployed_data.jsonc",
        ], timeout=60)
        assert result.returncode == 0
        stats = json.loads(result.stdout)
        assert stats["category"] == {
            "inserted": 1,
            "updated": 1,
            "removed_affected": 0,
        }
        result = _run([sys.executable, "test-app/bin/dev-deploy-data.py"], timeout=60)
        assert result.returncode == 0
        assert json.loads(result.stdout)["_integration"]["removed_affected"] == 1

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM _integration WHERE name = 'removed-from-model'")
                assert cur.fetchone() is None
        finally:
            conn.close()

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, description FROM category "
                    "WHERE name IN ('Deployed Hardware', 'Deployed Services') ORDER BY name"
                )
                assert cur.fetchall() == [
                    ("Deployed Hardware", "Hardware managed by deployed data"),
                    ("Deployed Services", "Services managed by deployed data"),
                ]
        finally:
            conn.close()

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
    def test_external_company_dummy_action_via_generated_caller(self):
        """The generated caller logs in and invokes a model-defined backend action."""
        returncode, response = _call_edge_function_script(
            "user1@test.com",
            "external-company-dummy-ok",
            {"id": 1},
            via_script=True,
        )

        assert returncode == 0
        assert response == {
            "status": 200,
            "body": {
                "status": "ok",
                "message": "Dummy OK received: external_company_name_1",
            },
        }

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

        version_filter = urllib.parse.urlencode({
            "root_concept": "eq.order",
            "root_concept_id": f"eq.{order_id}",
            "select": "concept,concept_id,concept_id_presentation,root_concept,root_concept_id,root_concept_id_presentation,change_type,operation,_updated_at",
            "order": "_updated_at.desc",
        })
        status, own_versions = _http_json(
            "GET",
            f"{api_url}/rest/v1/_version?{version_filter}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {user1_token}"},
        )
        assert status == 200
        assert {row["concept"] for row in own_versions} >= {"order", "order_item"}
        assert all(
            row["root_concept_id"] == order_id
            and row["concept_id"]
            and row["concept_id_presentation"]
            and row["root_concept_id_presentation"]
            and row["_updated_at"]
            for row in own_versions
        )

        user2_token = _login(api_url, anon_key, "user2@test.com")
        status, hidden_versions = _http_json(
            "GET",
            f"{api_url}/rest/v1/_version?{version_filter}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {user2_token}"},
        )
        assert status == 200
        assert hidden_versions == []

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
    def test_version_history_groups_part_of_relations_and_documents(self):
        """Version history is a user-facing audit contract across aggregate boundaries."""
        load_dotenv(Path('test-app/backend/.env'))
        db_url = os.getenv("DB_URL")
        assert db_url

        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM product WHERE sku = 'SEED-KBD-001'")
                product_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO category (name, slug) VALUES ('Version category', 'version-category') RETURNING id"
                )
                category_id = cur.fetchone()[0]
                cur.execute(
                    '''INSERT INTO "order" (
                           "order_date", "shipping_address_street", "shipping_address_city",
                           "shipping_address_province", "shipping_address_country", "state"
                       ) VALUES (NOW(), 'Version Street', 'Bilbao', 'Bizkaia', 'Spain', 'initial')
                       RETURNING id;'''
                )
                order_id = cur.fetchone()[0]
                cur.execute(
                    'INSERT INTO order_item ("order", product, quantity) VALUES (%s, %s, 1) RETURNING id;',
                    (order_id, product_id),
                )
                item_id = cur.fetchone()[0]
                cur.execute('UPDATE order_item SET quantity = 2 WHERE id = %s;', (item_id,))
                cur.execute(
                    '''INSERT INTO order_document (order_id, tag, storage_path)
                       VALUES (%s, 'invoice', %s) RETURNING id;''',
                    (order_id, f'{order_id}/invoice/version-test.pdf'),
                )
                document_id = cur.fetchone()[0]
                cur.execute(
                    'INSERT INTO category_product (category_id, product_id) VALUES (%s, %s);',
                    (category_id, product_id),
                )

                cur.execute(
                    '''SELECT concept, root_concept, root_concept_id, change_type, operation,
                              transaction_id, before, changed, _updated_at
                       FROM _version
                       WHERE transaction_id = txid_current()::text
                       ORDER BY id;'''
                )
                versions = cur.fetchall()
                assert versions
                assert all(row[5] == versions[0][5] for row in versions)
                assert all(row[8] is not None for row in versions)

                item_update = next(
                    row for row in versions
                    if row[0] == 'order_item' and row[4] == 'update' and 'quantity' in row[7]
                )
                assert item_update[1:3] == ('order', order_id)
                assert item_update[6]['quantity'] == 1
                assert item_update[7]['quantity'] == 2

                document_insert = next(
                    row for row in versions
                    if row[0] == 'order_document' and row[4] == 'insert'
                )
                assert document_insert[1:5] == ('order', order_id, 'documents', 'insert')
                assert document_insert[7].get('id') is None
                assert document_insert[6] is None

                relation_inserts = [
                    row for row in versions
                    if row[0] == 'category_product' and row[3] == 'relations'
                ]
                assert {(row[1], row[2]) for row in relation_inserts} == {
                    ('category', category_id), ('product', product_id),
                }
                assert all(row[7]['category_id'] == category_id for row in relation_inserts)

                # A regular related_to field is versioned against its own record,
                # unlike the part_of order_item case above. This is the data the
                # edit form uses to restore the previous selector value.
                cur.execute(
                    "INSERT INTO product (name, sku, price) "
                    "VALUES ('Version alternative', 'VERSION-RELATED-TO-001', 15.00) "
                    "RETURNING id"
                )
                alternative_product_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO field_checker (a_string, a_product) "
                    "VALUES ('Version relation checker', %s) RETURNING id",
                    (product_id,),
                )
                field_checker_id = cur.fetchone()[0]
                cur.execute(
                    "UPDATE field_checker SET a_product = %s WHERE id = %s",
                    (alternative_product_id, field_checker_id),
                )
                cur.execute(
                    '''SELECT root_concept, root_concept_id, change_type, operation,
                              before, changed
                       FROM _version
                       WHERE concept = 'field_checker' AND concept_id = %s
                         AND operation = 'update'
                       ORDER BY id DESC LIMIT 1;''',
                    (field_checker_id,),
                )
                related_to_update = cur.fetchone()
                assert related_to_update[:4] == (
                    'field_checker', field_checker_id, 'fields', 'update',
                )
                assert related_to_update[4]['a_product'] == product_id
                assert related_to_update[5]['a_product'] == alternative_product_id

                cur.execute(
                    "INSERT INTO category (name, slug) VALUES ('Version tree', 'version-tree') RETURNING id"
                )
                tree_root = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO category (parent, name, slug) VALUES (%s, 'Version child', 'version-child') RETURNING id",
                    (tree_root,),
                )
                tree_child = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO category (parent, name, slug) VALUES (%s, 'Version grandchild', 'version-grandchild') RETURNING id",
                    (tree_child,),
                )
                tree_grandchild = cur.fetchone()[0]
                cur.execute(
                    "UPDATE category SET description = 'Versioned tree update' WHERE id = %s",
                    (tree_grandchild,),
                )
                cur.execute(
                    '''SELECT root_concept, root_concept_id, changed FROM _version
                       WHERE concept = 'category' AND operation = 'update'
                         AND concept_id = %s
                       ORDER BY id DESC LIMIT 1;''',
                    (tree_grandchild,),
                )
                recursive_update = cur.fetchone()
                assert recursive_update[:2] == ('category', tree_root)
                assert recursive_update[2]['description'] == 'Versioned tree update'

                cur.execute('DELETE FROM order_item WHERE id = %s;', (item_id,))
                cur.execute(
                    '''SELECT root_concept, root_concept_id, operation, before, changed
                       FROM _version WHERE concept = 'order_item'
                       ORDER BY id DESC LIMIT 1;'''
                )
                deleted = cur.fetchone()
                assert deleted[:3] == ('order', order_id, 'delete')
                assert deleted[3]['id'] == item_id
                assert deleted[4] == {}

                cur.execute('SAVEPOINT immutable_version_probe')
                with pytest.raises(psycopg2.Error):
                    cur.execute(
                        '''INSERT INTO _version (
                               concept, concept_id, concept_id_presentation,
                               root_concept, root_concept_id, root_concept_id_presentation,
                               change_type, operation, transaction_id, changed
                           ) VALUES ('order', 1, '#1', 'order', 1, '#1',
                                     'fields', 'insert', 'manual', '{}');'''
                    )
                cur.execute('ROLLBACK TO SAVEPOINT immutable_version_probe')

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
