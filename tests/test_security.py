import pytest
from unibizkit.schema_processor import SchemaProcessor
import os
import psycopg2
from dotenv import load_dotenv

def test_security_rules_merging():
    schema = {
        "concepts": [
            {"name": "product", "plural_name": "products", "fields": [{"name": "f1", "type": "string", "size": "s", "required": False}], "id_presentation": {"fields": []}},
            {"name": "order", "plural_name": "orders", "fields": [{"name": "f1", "type": "string", "size": "s", "required": False}], "id_presentation": {"fields": []}}
        ]
    }
    
    security_config = {
        "authentication_required": True,
        "rules_level_1": [
            {"role": "user", "concept": "*", "access": "read"},
            {"role": "admin", "concept": "*", "access": "write"}
        ],
        "rules_level_2": [
            {"role": "user", "concept": "product", "access": "write"}
        ],
        "rules_level_3": [
            {"role": "user", "concept": "product", "field": "f1", "access": "read"}
        ]
    }
    
    processor = SchemaProcessor(schema, security_config=security_config)
    processed = processor.process()
    
    _acl = processor.security_extended["_acl"]
    
    # Helper to find a rule: concept -> field -> role -> access
    def find_rule(role, concept, field="f1"):
        concept_acl = _acl.get(concept, {})
        field_rule = concept_acl["_fields"].get(field, {}).get(role)
        if field_rule:
            return field_rule
        return concept_acl["_main"].get(role)

    # User rules:
    # Level 1: user product read, user order read
    # Level 2: user product write (overrides L1)
    # Level 3: user product read (overrides L2)
    assert find_rule("user", "product") == "read"
    assert find_rule("user", "order") == "read"
    
    # Admin rules:
    # Level 1: admin product write, admin order write
    assert find_rule("admin", "product") == "write"
    assert find_rule("admin", "order") == "write"

    # Final cleanup check: should NOT be removed anymore
    for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
        assert level in processor.security_extended, f"{level} should be preserved in processed security"

def test_security_rules_default_level_1():
    schema = {
        "concepts": [
            {"name": "product", "plural_name": "products", "fields": [{"name": "f1", "type": "string", "size": "s", "required": False}], "id_presentation": {"fields": []}}
        ]
    }
    
    # No rules_level_1 provided
    security_config = {
        "authentication_required": True
    }
    
    processor = SchemaProcessor(schema, security_config=security_config)
    processor.process()
    
    _acl = processor.security_extended["_acl"]
    
    def find_rule(role, concept, field="f1"):
        concept_acl = _acl.get(concept, {})
        field_rule = concept_acl["_fields"].get(field, {}).get(role)
        if field_rule:
            return field_rule
        return concept_acl["_main"].get(role)

    # Should use default: admin write, user read
    assert find_rule("admin", "product") == "write"
    assert find_rule("user", "product") == "read"

    # Final cleanup check
    for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
        assert level in processor.security_extended, f"{level} should be preserved in processed security"

def test_security_rules_complex_override():
    schema = {
        "concepts": [
            {"name": "product", "plural_name": "products", "fields": [{"name": "f1", "type": "string", "size": "s", "required": False}], "id_presentation": {"fields": []}},
            {"name": "order", "plural_name": "orders", "fields": [{"name": "f1", "type": "string", "size": "s", "required": False}], "id_presentation": {"fields": []}}
        ]
    }
    
    security_config = {
        "authentication_required": True,
        "rules_level_1": [
            {"role": "user", "concept": "*", "access": "read"}
        ],
        "rules_level_2": [
            {"role": "user", "concept": "*", "access": "write"} # Global override
        ],
        "rules_level_3": [
            {"role": "user", "concept": "order", "access": "read"} # Specific exception
        ]
    }
    
    processor = SchemaProcessor(schema, security_config=security_config)
    processor.process()
    
    _acl = processor.security_extended["_acl"]
    
    def find_rule(role, concept, field="f1"):
        concept_acl = _acl.get(concept, {})
        field_rule = concept_acl["_fields"].get(field, {}).get(role)
        if field_rule:
            return field_rule
        return concept_acl["_main"].get(role)

    assert find_rule("user", "product") == "write"
    assert find_rule("user", "order") == "read"

    # Final cleanup check
    for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
        assert level in processor.security_extended, f"{level} should be preserved in processed security"

def test_security_extended_file_validation():
    import json
    import jsonschema
    from pathlib import Path
    
    # Rutas a los archivos generados en test-app
    schema_path = Path("test-app/security_extended_schema.json")
    data_path = Path("test-app/security_extended.json")
    
    # Comprobar que los archivos existen para evitar fallos si no se ha ejecutado el generador
    if not schema_path.exists() or not data_path.exists():
        pytest.skip("Archivos test-app/security_extended*.json no encontrados. Ejecute el CLI primero.")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
        
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        pytest.fail(f"La validación del archivo falló: {e.message}")

@pytest.mark.integration
def test_owner_write_rls():
    """Test RLS owner_write capabilities."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")
        
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    
    with conn.cursor() as cur:
        # Get users from auth.users
        cur.execute("SELECT id, email FROM auth.users")
        users = cur.fetchall()
        user_ids = {email: uid for uid, email in users}
        
        user1_id = user_ids.get("user1@test.com")
        user2_id = user_ids.get("user2@test.com")
        admin_id = user_ids.get("admin@test.com")
        
        if not all([user1_id, user2_id, admin_id]):
            pytest.skip(f"Required users not found in DB. Found: {user_ids}")
            
        try:
            # We must use transaction to set local config safely
            # Note: psycopg2 autocommit is True, so we must manually manage the transaction for SET LOCAL
            cur.execute("BEGIN;")
            
            # --- Test as user1 ---
            cur.execute("SET LOCAL ROLE authenticated;")
            # Simulating user1
            cur.execute(f"SELECT set_config('request.jwt.claims', '{{\"sub\": \"{user1_id}\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}', true);")
            
            # Need a customer for the order (from sample data, customer 1 should exist, but let's safely select one)
            cur.execute('SELECT id FROM "customer" LIMIT 1;')
            customer_id = cur.fetchone()[0]
            
            # Create an order as user1
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address, security_owner_id)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 100.00, 'pending', 'User 1 Address', '{user1_id}')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            
            # Can user1 read it?
            cur.execute(f'SELECT id FROM "order" WHERE id = {order_id}')
            assert cur.fetchone() is not None, "user1 should be able to read their own order"
            
            # --- Switch to user2 ---
            cur.execute(f"SELECT set_config('request.jwt.claims', '{{\"sub\": \"{user2_id}\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}', true);")
            cur.execute(f'SELECT id FROM "order" WHERE id = {order_id}')
            assert cur.fetchone() is None, "user2 should NOT be able to read user1's order"
            
            # --- Switch to admin ---
            cur.execute(f"SELECT set_config('request.jwt.claims', '{{\"sub\": \"{admin_id}\", \"app_metadata\": {{\"roles\": [\"admin\"]}}}}', true);")
            cur.execute(f'SELECT id FROM "order" WHERE id = {order_id}')
            assert cur.fetchone() is not None, "admin should be able to read all orders"
            
        finally:
            cur.execute("ROLLBACK;")

@pytest.mark.integration
def test_security_owner_id_is_not_updatable():
    """Test that security_owner_id cannot be updated by admin or user1."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM auth.users")
        users = cur.fetchall()
        user_ids = {email: uid for uid, email in users}

        user1_id = user_ids.get("user1@test.com")
        admin_id = user_ids.get("admin@test.com")

        if not all([user1_id, admin_id]):
            pytest.skip(f"Required users not found in DB. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        # Create an order as superuser (bypassing RLS)
        cur.execute(f"""
            INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address, security_owner_id)
            VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'pending', 'Test Address', '{user1_id}')
            RETURNING id;
        """)
        order_id = cur.fetchone()[0]

        def assert_cannot_update_owner_id(role_label, jwt_claims):
            """Returns True if the UPDATE was blocked, False if it silently succeeded."""
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{jwt_claims}', true);")
                cur.execute(f"UPDATE \"order\" SET security_owner_id = '{admin_id}' WHERE id = {order_id};")
                cur.execute(f'SELECT security_owner_id FROM "order" WHERE id = {order_id};')
                row = cur.fetchone()
                # If UPDATE succeeded without error, check value didn't change
                assert row is not None and str(row[0]) == str(user1_id), \
                    f"{role_label} should NOT be able to change security_owner_id, but it changed to {row[0] if row else 'N/A'}"
            except psycopg2.Error:
                # UPDATE was blocked by REVOKE — this is the expected outcome
                pass
            finally:
                cur.execute("ROLLBACK;")

        try:
            user1_claims = f'{{\"sub\": \"{user1_id}\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}'
            admin_claims = f'{{\"sub\": \"{admin_id}\", \"app_metadata\": {{\"roles\": [\"admin\"]}}}}'
            assert_cannot_update_owner_id("user1", user1_claims)
            assert_cannot_update_owner_id("admin", admin_claims)
        finally:
            # Clean up the order as superuser
            cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')

@pytest.mark.integration
def test_created_at_is_immutable():
    """Test that _created_at cannot be modified via UPDATE, even by admin."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM auth.users")
        user_ids = {email: uid for uid, email in cur.fetchall()}
        admin_id = user_ids.get("admin@test.com")
        if not admin_id:
            pytest.skip(f"Required users not found. Found: {user_ids}")

        # Get original _created_at of an existing product
        cur.execute('SELECT id, "_created_at" FROM "product" LIMIT 1;')
        product_id, original_created_at = cur.fetchone()

        admin_claims = f'{{"sub": "{admin_id}", "app_metadata": {{"roles": ["admin"]}}}}'
        cur.execute("BEGIN;")
        try:
            cur.execute("SET LOCAL ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{admin_claims}', true);")

            cur.execute(f"""UPDATE "product" SET "_created_at" = '2020-01-01T00:00:00Z' WHERE id = {product_id};""")
            cur.execute(f'SELECT "_created_at" FROM "product" WHERE id = {product_id};')
            row = cur.fetchone()
            assert row is not None and row[0] == original_created_at, \
                f"_created_at should be immutable, but changed from {original_created_at} to {row[0]}"
        except psycopg2.Error:
            # Exception means the UPDATE was blocked — acceptable
            pass
        finally:
            cur.execute("ROLLBACK;")


@pytest.mark.integration
def test_timestamps_cannot_be_forged_on_insert():
    """Test that _created_at and _updated_at are system-controlled on INSERT."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM auth.users")
        user_ids = {email: uid for uid, email in cur.fetchall()}
        user1_id = user_ids.get("user1@test.com")
        if not user1_id:
            pytest.skip(f"Required users not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        user_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
        fake_ts = '2020-01-01T00:00:00+00:00'

        cur.execute("BEGIN;")
        try:
            cur.execute("SET LOCAL ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user_claims}', true);")

            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address,
                    security_owner_id, "_created_at", "_updated_at")
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'pending', 'Test',
                    '{user1_id}', '{fake_ts}', '{fake_ts}')
                RETURNING "_created_at", "_updated_at";
            """)
            created_at, updated_at = cur.fetchone()

            from datetime import datetime, timezone
            fake_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
            assert created_at != fake_dt, \
                f"_created_at should be system-controlled, but accepted forged value: {created_at}"
            assert updated_at != fake_dt, \
                f"_updated_at should be system-controlled, but accepted forged value: {updated_at}"
        except psycopg2.Error:
            # INSERT blocked entirely is also acceptable
            pass
        finally:
            cur.execute("ROLLBACK;")


@pytest.mark.integration
def test_order_document_owner_isolation():
    """Test that user2 cannot access user1's order document via DB table or Storage API.

    Verifies two layers of protection:
    1. DB RLS: the order_document table enforces ownership via JOIN on order.security_owner_id
    2. Storage RLS: the storage bucket enforces ownership via the same JOIN
    """
    import requests as req

    load_dotenv("test-app/backend/.env")
    load_dotenv("test-app/frontend/.env")
    db_url = os.getenv("DB_URL")
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("REACT_APP_SUPABASE_KEY")
    if not db_url or not supabase_url or not anon_key:
        pytest.skip("Missing DB_URL / SUPABASE_URL / REACT_APP_SUPABASE_KEY.")

    # --- Sign in as user1 and user2 via Auth API to get real JWTs ---
    def sign_in(email, password):
        resp = req.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=10,
        )
        assert resp.status_code == 200, f"Sign-in failed for {email}: {resp.text}"
        return resp.json()["access_token"]

    user1_token = sign_in("user1@test.com", "useruser")
    user2_token = sign_in("user2@test.com", "useruser")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    storage_path = None
    order_id = None
    bucket = "order-documents"
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM auth.users")
        user_ids = {email: uid for uid, email in cur.fetchall()}
        user1_id = user_ids.get("user1@test.com")
        user2_id = user_ids.get("user2@test.com")
        if not user1_id or not user2_id:
            pytest.skip(f"Required users not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
        user2_claims = f'{{"sub": "{user2_id}", "app_metadata": {{"roles": ["user"]}}}}'

        try:
            # --- Insert order and document as user1 (committed, so storage policy JOIN can see them) ---
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")

            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address, security_owner_id)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 200.00, 'pending', 'User1 Address', '{user1_id}')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]

            # Upload file to Storage as user1
            storage_path = f"{order_id}/invoice/test_isolation.txt"
            upload_resp = req.post(
                f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}",
                headers={"Authorization": f"Bearer {user1_token}", "apikey": anon_key},
                data=b"user1 private invoice",
                timeout=10,
            )
            assert upload_resp.status_code in (200, 201), \
                f"user1 upload failed: {upload_resp.status_code} {upload_resp.text}"

            # Insert the document DB record (committed so storage policy can JOIN on it)
            cur.execute(f"""
                INSERT INTO "order_document" (order_id, tag, storage_path)
                VALUES ({order_id}, 'invoice', '{storage_path}')
                RETURNING id;
            """)
            doc_id = cur.fetchone()[0]

            # --- Layer 1: DB RLS ---
            cur.execute(f'SELECT id FROM "order_document" WHERE id = {doc_id}')
            assert cur.fetchone() is not None, "user1 should be able to read their own order_document row"

            cur.execute(f"SELECT set_config('request.jwt.claims', '{user2_claims}', false);")
            cur.execute(f'SELECT id FROM "order_document" WHERE id = {doc_id}')
            assert cur.fetchone() is None, \
                "user2 should NOT be able to read user1's order_document row (DB RLS violation)"

            # --- Layer 2: Storage RLS ---
            # user1 can download their own file
            dl_user1 = req.get(
                f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}",
                headers={"Authorization": f"Bearer {user1_token}", "apikey": anon_key},
                timeout=10,
            )
            assert dl_user1.status_code == 200, \
                f"user1 should be able to download their own file, got {dl_user1.status_code}: {dl_user1.text}"

            # user2 cannot download user1's file
            dl_user2 = req.get(
                f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}",
                headers={"Authorization": f"Bearer {user2_token}", "apikey": anon_key},
                timeout=10,
            )
            assert dl_user2.status_code in (400, 403, 404), \
                f"user2 should NOT be able to download user1's file, got {dl_user2.status_code}: {dl_user2.text}"

        finally:
            # Reset role and clean up committed data
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')
            if storage_path and service_role_key:
                req.delete(
                    f"{supabase_url}/storage/v1/object/{bucket}",
                    headers={
                        "Authorization": f"Bearer {service_role_key}",
                        "apikey": anon_key,
                        "Content-Type": "application/json",
                    },
                    json={"prefixes": [storage_path]},
                    timeout=10,
                )


@pytest.mark.integration
def test_order_document_upload_authorization():
    """Test storage upload authorization for order-documents bucket.

    Verifies:
    - user2 cannot upload to a non-existent order ID path
    - user2 cannot upload to a path belonging to user1's order
    - admin can upload to user1's order path (write access, no ownership restriction)
    """
    import requests as req

    load_dotenv("test-app/backend/.env")
    load_dotenv("test-app/frontend/.env")
    db_url = os.getenv("DB_URL")
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("REACT_APP_SUPABASE_KEY")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not db_url or not supabase_url or not anon_key:
        pytest.skip("Missing DB_URL / SUPABASE_URL / REACT_APP_SUPABASE_KEY.")

    def sign_in(email, password):
        resp = req.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=10,
        )
        assert resp.status_code == 200, f"Sign-in failed for {email}: {resp.text}"
        return resp.json()["access_token"]

    user2_token = sign_in("user2@test.com", "useruser")
    admin_token = sign_in("admin@test.com", "adminadmin")

    bucket = "order-documents"
    uploaded_paths = []

    def upload(token, path, content=b"test"):
        return req.post(
            f"{supabase_url}/storage/v1/object/{bucket}/{path}",
            headers={"Authorization": f"Bearer {token}", "apikey": anon_key},
            data=content,
            timeout=10,
        )

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    order_id = None

    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM auth.users")
        user_ids = {email: uid for uid, email in cur.fetchall()}
        user1_id = user_ids.get("user1@test.com")
        if not user1_id:
            pytest.skip(f"user1 not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        try:
            # Create an order owned by user1 (committed so storage policy can JOIN on it)
            user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address, security_owner_id)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'pending', 'User1 Address', '{user1_id}')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            nonexistent_id = 999999999

            # user2 cannot upload to a non-existent order ID path
            r = upload(user2_token, f"{nonexistent_id}/invoice/u2_fake.txt")
            assert r.status_code not in (200, 201), \
                f"user2 should NOT upload to non-existent order path, got {r.status_code}: {r.text}"

            # user2 cannot upload to user1's order path
            r = upload(user2_token, f"{order_id}/invoice/u2_steal.txt")
            assert r.status_code not in (200, 201), \
                f"user2 should NOT upload to user1's order path, got {r.status_code}: {r.text}"

            # admin can upload to user1's order path
            admin_path = f"{order_id}/invoice/admin_upload.txt"
            r = upload(admin_token, admin_path)
            assert r.status_code in (200, 201), \
                f"admin should be able to upload to any order path, got {r.status_code}: {r.text}"
            uploaded_paths.append(admin_path)

        finally:
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')
            if uploaded_paths and service_role_key:
                req.delete(
                    f"{supabase_url}/storage/v1/object/{bucket}",
                    headers={
                        "Authorization": f"Bearer {service_role_key}",
                        "apikey": anon_key,
                        "Content-Type": "application/json",
                    },
                    json={"prefixes": uploaded_paths},
                    timeout=10,
                )
