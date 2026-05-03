import pytest
from unibizkit.schema_processor import SchemaProcessor
import os
import json
import psycopg2
from dotenv import load_dotenv

_MINIMAL_CONCEPT = {
    "name": "item",
    "plural_name": "items",
    "fields": [{"name": "f1", "type": "string", "size": "s", "required": False}],
    "id_presentation": {"fields": []},
}

def _make_processor(rules_level_2=None, roles=None):
    security_config = {
        "authentication_required": True,
        "rules_level_1": [
            {"role": "admin", "concept": "*", "access": "write"},
            {"role": "user",  "concept": "*", "access": "read"},
        ],
        "rules_level_2": rules_level_2 or [],
    }
    if roles:
        security_config["roles"] = roles
    schema = {"concepts": [_MINIMAL_CONCEPT]}
    return SchemaProcessor(schema, security_config=security_config)


def test_anon_read_appears_in_acl():
    """_anon with read access should appear in _acl._main for the target concept."""
    processor = _make_processor(
        rules_level_2=[{"role": "_anon", "concept": "item", "access": "read"}]
    )
    processor.process()
    acl = processor.security_extended["_acl"]
    assert acl.get("item", {}).get("_main", {}).get("_anon") == "read"


def test_anon_write_raises_error():
    """_anon with write access must raise ValueError at process time."""
    processor = _make_processor(
        rules_level_2=[{"role": "_anon", "concept": "item", "access": "write"}]
    )
    with pytest.raises(ValueError, match="_anon"):
        processor.process()


def test_anon_owner_write_raises_error():
    """_anon with owner_write access must raise ValueError at process time."""
    processor = _make_processor(
        rules_level_2=[{"role": "_anon", "concept": "item", "access": "owner_write"}]
    )
    with pytest.raises(ValueError, match="_anon"):
        processor.process()


def test_anon_not_required_in_roles_list():
    """_anon does not need to be declared in the roles list."""
    processor = _make_processor(
        rules_level_2=[{"role": "_anon", "concept": "item", "access": "read"}],
        roles=[{"name": "admin"}, {"name": "user"}],
    )
    processor.process()
    role_names = [r["name"] for r in processor.security_extended["roles"]]
    assert "_anon" not in role_names  # not polluted into the roles list
    acl = processor.security_extended["_acl"]
    assert acl["item"]["_main"].get("_anon") == "read"

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
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 100.00, 'initial', 'User 1 Address')
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

        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
        cur.execute("SET ROLE authenticated;")
        cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
        cur.execute(f"""
            INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
            VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'initial', 'Test Address')
            RETURNING id;
        """)
        order_id = cur.fetchone()[0]
        cur.execute("RESET ROLE;")
        cur.execute("SELECT set_config('request.jwt.claims', '', false);")

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
                    "_created_at", "_updated_at")
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'initial', 'Test',
                    '{fake_ts}', '{fake_ts}')
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
    load_dotenv("test-app/frontend/.env.development")
    db_url = os.getenv("DB_URL")
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("VITE_SUPABASE_KEY")
    if not db_url or not supabase_url or not anon_key:
        pytest.skip("Missing DB_URL / SUPABASE_URL / VITE_SUPABASE_KEY.")

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
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 200.00, 'initial', 'User1 Address')
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

            # Trigger created the record automatically on upload
            cur.execute(f"SELECT id FROM \"order_document\" WHERE order_id = {order_id} AND tag = 'invoice'")
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
    load_dotenv("test-app/frontend/.env.development")
    db_url = os.getenv("DB_URL")
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("VITE_SUPABASE_KEY")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not db_url or not supabase_url or not anon_key:
        pytest.skip("Missing DB_URL / SUPABASE_URL / VITE_SUPABASE_KEY.")

    def sign_in(email, password):
        resp = req.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=10,
        )
        assert resp.status_code == 200, f"Sign-in failed for {email}: {resp.text}"
        return resp.json()["access_token"]

    # Read credentials from security_extended.json to be resilient
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        security_config = json.load(f)
        admin_data = next(u for u in security_config["users"] if "admin" in u["roles"])
        user2_data = next(u for u in security_config["users"] if u["email"] == "user2@test.com")
        
    user2_token = sign_in(user2_data["email"], user2_data["password"])
    admin_token = sign_in(admin_data["email"], admin_data["password"])

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
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'initial', 'User1 Address')
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


@pytest.mark.integration
def test_order_item_create_restricted_by_order_state():
    """Test that user1 can create an order_item when the parent order state is 'initial',
    but cannot when the order state is 'ordered'."""
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
            pytest.skip(f"user1 not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]
        cur.execute('SELECT id FROM "product" LIMIT 1;')
        product_id = cur.fetchone()[0]

        order_id = None
        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'

        try:
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 100.00, 'initial', 'Test Address')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            # --- Test 1: state='initial' → user1 CAN create order_item ---
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"""
                    INSERT INTO "order_item" ("order", product, quantity, unit_price)
                    VALUES ({order_id}, {product_id}, 2, 10.00)
                    RETURNING id;
                """)
                row = cur.fetchone()
                assert row is not None, "user1 should be able to create order_item when order state is 'initial'"
            finally:
                cur.execute("ROLLBACK;")

            # Advance order to state 'ordered' as superuser
            cur.execute(f"UPDATE \"order\" SET state = 'ordered' WHERE id = {order_id};")

            # --- Test 2: state='ordered' → user1 CANNOT create order_item ---
            created = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"""
                    INSERT INTO "order_item" ("order", product, quantity, unit_price)
                    VALUES ({order_id}, {product_id}, 1, 5.00)
                    RETURNING id;
                """)
                row = cur.fetchone()
                if row is not None:
                    created = True
            except psycopg2.Error:
                created = False
            finally:
                cur.execute("ROLLBACK;")

            assert not created, "user1 should NOT be able to create order_item when order state is 'ordered'"

        finally:
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')


@pytest.mark.integration
def test_order_document_create_restricted_by_order_state():
    """Test that user1 can insert an order_document when order state is 'initial',
    but cannot when the order state is 'ordered'."""
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
            pytest.skip(f"user1 not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        order_id = None
        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'

        try:
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 100.00, 'initial', 'Test Address')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            # --- Test 1: state='initial' → user1 CAN insert order_document ---
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"""
                    INSERT INTO "order_document" (order_id, tag, storage_path)
                    VALUES ({order_id}, 'invoice', '{order_id}/invoice/test.pdf')
                    RETURNING id;
                """)
                row = cur.fetchone()
                assert row is not None, "user1 should be able to insert order_document when order state is 'initial'"
            finally:
                cur.execute("ROLLBACK;")

            # Advance order to state 'ordered' as superuser
            cur.execute(f"UPDATE \"order\" SET state = 'ordered' WHERE id = {order_id};")

            # --- Test 2: state='ordered' → user1 CANNOT insert order_document ---
            created = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"""
                    INSERT INTO "order_document" (order_id, tag, storage_path)
                    VALUES ({order_id}, 'receipt', '{order_id}/receipt/test.pdf')
                    RETURNING id;
                """)
                row = cur.fetchone()
                if row is not None:
                    created = True
            except psycopg2.Error:
                created = False
            finally:
                cur.execute("ROLLBACK;")

            assert not created, "user1 should NOT be able to insert order_document when order state is 'ordered'"

        finally:
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')


@pytest.mark.integration
def test_order_workflow_state_transitions():
    """Test allowed and blocked state transitions:
    - user CAN move initial → ordered (placing the order)
    - user CANNOT move ordered → accepted or back to initial
    - admin CAN move ordered → accepted
    """
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
        admin_id = user_ids.get("admin@test.com")
        if not user1_id or not admin_id:
            pytest.skip(f"Required users not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
        admin_claims = f'{{"sub": "{admin_id}", "app_metadata": {{"roles": ["admin"]}}}}'

        order_id = None
        try:
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 100.00, 'initial', 'Test')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            # user1 CAN move initial → ordered
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"UPDATE \"order\" SET state = 'ordered' WHERE id = {order_id};")
                cur.execute(f'SELECT state FROM "order" WHERE id = {order_id};')
                assert cur.fetchone()[0] == 'ordered', "user1 should be able to move order to 'ordered'"
            finally:
                cur.execute("ROLLBACK;")

            cur.execute(f"UPDATE \"order\" SET state = 'ordered' WHERE id = {order_id};")

            # user1 CANNOT move ordered → accepted
            blocked = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"UPDATE \"order\" SET state = 'accepted' WHERE id = {order_id};")
            except psycopg2.Error:
                blocked = True
            finally:
                cur.execute("ROLLBACK;")
            assert blocked, "user1 should NOT be able to move order from 'ordered' to 'accepted'"

            # user1 CANNOT move ordered → initial
            blocked = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"UPDATE \"order\" SET state = 'initial' WHERE id = {order_id};")
            except psycopg2.Error:
                blocked = True
            finally:
                cur.execute("ROLLBACK;")
            assert blocked, "user1 should NOT be able to move order back to 'initial' from 'ordered'"

            # admin CAN move ordered → accepted
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{admin_claims}', true);")
                cur.execute(f"UPDATE \"order\" SET state = 'accepted' WHERE id = {order_id};")
                cur.execute(f'SELECT state FROM "order" WHERE id = {order_id};')
                assert cur.fetchone()[0] == 'accepted', "admin should be able to move order to 'accepted'"
            finally:
                cur.execute("ROLLBACK;")

        finally:
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')


@pytest.mark.integration
def test_order_item_cross_user_isolation():
    """Test that user2 cannot read or write user1's order_items."""
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
        user2_id = user_ids.get("user2@test.com")
        if not user1_id or not user2_id:
            pytest.skip(f"Required users not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]
        cur.execute('SELECT id FROM "product" LIMIT 1;')
        product_id = cur.fetchone()[0]

        order_id = item_id = None
        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
        user2_claims = f'{{"sub": "{user2_id}", "app_metadata": {{"roles": ["user"]}}}}'

        try:
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'initial', 'Test')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute(f"""
                INSERT INTO "order_item" ("order", product, quantity, unit_price)
                VALUES ({order_id}, {product_id}, 1, 10.00)
                RETURNING id;
            """)
            item_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            # user2 CANNOT read user1's order_item
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user2_claims}', true);")
                cur.execute(f'SELECT id FROM "order_item" WHERE id = {item_id};')
                assert cur.fetchone() is None, "user2 should NOT be able to read user1's order_item"
            finally:
                cur.execute("ROLLBACK;")

            # user2 CANNOT insert order_item for user1's order
            blocked = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user2_claims}', true);")
                cur.execute(f"""
                    INSERT INTO "order_item" ("order", product, quantity, unit_price)
                    VALUES ({order_id}, {product_id}, 1, 5.00)
                    RETURNING id;
                """)
                if cur.fetchone() is None:
                    blocked = True
            except psycopg2.Error:
                blocked = True
            finally:
                cur.execute("ROLLBACK;")
            assert blocked, "user2 should NOT be able to insert order_item for user1's order"

            # user1 CAN read their own order_item
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f'SELECT id FROM "order_item" WHERE id = {item_id};')
                assert cur.fetchone() is not None, "user1 should be able to read their own order_item"
            finally:
                cur.execute("ROLLBACK;")

        finally:
            if item_id:
                cur.execute(f'DELETE FROM "order_item" WHERE id = {item_id};')
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')


@pytest.mark.integration
def test_order_item_update_delete_restricted_by_order_state():
    """Test that UPDATE and DELETE on order_item are blocked when order state != 'initial'."""
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
            pytest.skip(f"user1 not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]
        cur.execute('SELECT id FROM "product" LIMIT 1;')
        product_id = cur.fetchone()[0]

        order_id = item_id = None
        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'

        try:
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'initial', 'Test')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute(f"""
                INSERT INTO "order_item" ("order", product, quantity, unit_price)
                VALUES ({order_id}, {product_id}, 1, 10.00)
                RETURNING id;
            """)
            item_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            # user1 CAN update order_item when state='initial'
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f'UPDATE "order_item" SET quantity = 2 WHERE id = {item_id};')
            finally:
                cur.execute("ROLLBACK;")

            cur.execute(f"UPDATE \"order\" SET state = 'ordered' WHERE id = {order_id};")

            # user1 CANNOT update order_item when state='ordered'
            blocked = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f'UPDATE "order_item" SET quantity = 3 WHERE id = {item_id};')
            except psycopg2.Error:
                blocked = True
            finally:
                cur.execute("ROLLBACK;")
            assert blocked, "user1 should NOT be able to UPDATE order_item when order state is 'ordered'"

            # user1 CANNOT delete order_item when state='ordered' (RLS silently ignores the row)
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f'DELETE FROM "order_item" WHERE id = {item_id};')
                assert cur.rowcount == 0, "user1 should NOT be able to DELETE order_item when order state is 'ordered'"
            finally:
                cur.execute("ROLLBACK;")

        finally:
            if item_id:
                cur.execute(f'DELETE FROM "order_item" WHERE id = {item_id};')
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')


@pytest.mark.integration
def test_order_document_update_delete_restricted_by_order_state():
    """Test that UPDATE and DELETE on order_document are blocked when order state != 'initial'."""
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
            pytest.skip(f"user1 not found. Found: {user_ids}")

        cur.execute("SELECT id FROM customer LIMIT 1;")
        customer_id = cur.fetchone()[0]

        order_id = doc_id = None
        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'

        try:
            cur.execute("SET ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', false);")
            cur.execute(f"""
                INSERT INTO "order" (customer, order_date, total_amount, state, shipping_address)
                VALUES ({customer_id}, CURRENT_TIMESTAMP, 50.00, 'initial', 'Test')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute(f"""
                INSERT INTO "order_document" (order_id, tag, storage_path)
                VALUES ({order_id}, 'invoice', '{order_id}/invoice/test.pdf')
                RETURNING id;
            """)
            doc_id = cur.fetchone()[0]
            cur.execute("RESET ROLE;")
            cur.execute("SELECT set_config('request.jwt.claims', '', false);")

            # user1 CAN update order_document when state='initial'
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"UPDATE \"order_document\" SET storage_path = '{order_id}/invoice/v2.pdf' WHERE id = {doc_id};")
            finally:
                cur.execute("ROLLBACK;")

            cur.execute(f"UPDATE \"order\" SET state = 'ordered' WHERE id = {order_id};")

            # user1 CANNOT update order_document when state='ordered'
            blocked = False
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f"UPDATE \"order_document\" SET storage_path = '{order_id}/invoice/v3.pdf' WHERE id = {doc_id};")
            except psycopg2.Error:
                blocked = True
            finally:
                cur.execute("ROLLBACK;")
            assert blocked, "user1 should NOT be able to UPDATE order_document when order state is 'ordered'"

            # user1 CANNOT delete order_document when state='ordered' (RLS silently ignores the row)
            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE authenticated;")
                cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
                cur.execute(f'DELETE FROM "order_document" WHERE id = {doc_id};')
                assert cur.rowcount == 0, "user1 should NOT be able to DELETE order_document when order state is 'ordered'"
            finally:
                cur.execute("ROLLBACK;")

        finally:
            if doc_id:
                cur.execute(f'DELETE FROM "order_document" WHERE id = {doc_id};')
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')


@pytest.mark.integration
def test_admin_field_write_restriction():
    """Test that user cannot write product.admin_field (field-level trigger), but admin can."""
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
        admin_id = user_ids.get("admin@test.com")
        if not user1_id or not admin_id:
            pytest.skip(f"Required users not found. Found: {user_ids}")

        cur.execute('SELECT id FROM "product" LIMIT 1;')
        product_id = cur.fetchone()[0]

        user1_claims = f'{{"sub": "{user1_id}", "app_metadata": {{"roles": ["user"]}}}}'
        admin_claims = f'{{"sub": "{admin_id}", "app_metadata": {{"roles": ["admin"]}}}}'

        # user1 CANNOT update existing product's admin_field
        blocked = False
        cur.execute("BEGIN;")
        try:
            cur.execute("SET LOCAL ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{user1_claims}', true);")
            cur.execute(f"UPDATE \"product\" SET admin_field = 'hacked' WHERE id = {product_id};")
        except psycopg2.Error:
            blocked = True
        finally:
            cur.execute("ROLLBACK;")
        assert blocked, "user1 should NOT be able to update product.admin_field"

        # admin CAN update product's admin_field
        cur.execute("BEGIN;")
        try:
            cur.execute("SET LOCAL ROLE authenticated;")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{admin_claims}', true);")
            cur.execute(f"UPDATE \"product\" SET admin_field = 'admin_value' WHERE id = {product_id};")
        finally:
            cur.execute("ROLLBACK;")


@pytest.mark.integration
def test_order_lifecycle_via_api():
    """Full lifecycle test via Supabase API:
    1. user1 creates an order in 'initial' state and uploads a document
    2. user2 tries to see the order — gets nothing (owner isolation)
    3. user1 advances the order to 'ordered'
    4. user1 downloads the document — succeeds
    5. user1 tries to update the document record — fails (order no longer in 'initial')
    """
    import requests as req

    load_dotenv("test-app/backend/.env")
    load_dotenv("test-app/frontend/.env.development")
    db_url = os.getenv("DB_URL")
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("VITE_SUPABASE_KEY")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not db_url or not supabase_url or not anon_key:
        pytest.skip("Missing DB_URL / SUPABASE_URL / VITE_SUPABASE_KEY.")

    def sign_in(email, password):
        resp = req.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=10,
        )
        assert resp.status_code == 200, f"Sign-in failed for {email}: {resp.text}"
        return resp.json()["access_token"]

    def api_headers(token):
        return {"Authorization": f"Bearer {token}", "apikey": anon_key, "Content-Type": "application/json"}

    with open(os.path.abspath("test-app/security_extended.json")) as f:
        users = json.load(f)["users"]
    user_users = [u for u in users if "user" in u["roles"]]
    if len(user_users) < 2:
        pytest.skip("Need at least 2 users with role 'user' in security_extended.json.")
    user1_data, user2_data = user_users[0], user_users[1]

    user1_token = sign_in(user1_data["email"], user1_data["password"])
    user2_token = sign_in(user2_data["email"], user2_data["password"])

    bucket = "order-documents"
    order_id = None
    storage_path = None

    # Get a valid customer_id via API as user1
    r = req.get(f"{supabase_url}/rest/v1/customer?limit=1&select=id",
                headers=api_headers(user1_token), timeout=10)
    assert r.status_code == 200 and r.json(), "Could not fetch a customer via API."
    customer_id = r.json()[0]["id"]

    try:
        # 1. user1 creates an order in 'initial' state
        r = req.post(
            f"{supabase_url}/rest/v1/order",
            headers={**api_headers(user1_token), "Prefer": "return=representation"},
            json={"customer": customer_id, "order_date": "2024-01-01", "total_amount": 150.00,
                  "state": "initial", "shipping_address": "Lifecycle Test Address"},
            timeout=10,
        )
        assert r.status_code in (200, 201), f"user1 failed to create order: {r.status_code} {r.text}"
        order_id = r.json()[0]["id"]

        # user1 uploads a document to Storage
        storage_path = f"{order_id}/invoice/lifecycle_test.txt"
        r = req.post(
            f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}",
            headers={"Authorization": f"Bearer {user1_token}", "apikey": anon_key},
            data=b"lifecycle invoice content",
            timeout=10,
        )
        assert r.status_code in (200, 201), f"user1 failed to upload document: {r.status_code} {r.text}"

        # Trigger created the record automatically on upload - retrieve the id
        r = req.get(
            f"{supabase_url}/rest/v1/order_document?order_id=eq.{order_id}&tag=eq.invoice",
            headers=api_headers(user1_token),
            timeout=10,
        )
        assert r.status_code == 200 and r.json(), f"order_document not found after upload: {r.status_code} {r.text}"
        doc_id = r.json()[0]["id"]

        # 2. user2 tries to see the order — should get empty list
        r = req.get(
            f"{supabase_url}/rest/v1/order?id=eq.{order_id}",
            headers=api_headers(user2_token),
            timeout=10,
        )
        assert r.status_code == 200 and r.json() == [], \
            f"user2 should NOT see user1's order, got: {r.status_code} {r.text}"

        # 3. user1 advances the order to 'ordered'
        r = req.patch(
            f"{supabase_url}/rest/v1/order?id=eq.{order_id}",
            headers={**api_headers(user1_token), "Prefer": "return=representation"},
            json={"state": "ordered"},
            timeout=10,
        )
        assert r.status_code in (200, 204), f"user1 failed to advance order state: {r.status_code} {r.text}"

        # 4. user1 downloads the document — should succeed
        r = req.get(
            f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}",
            headers={"Authorization": f"Bearer {user1_token}", "apikey": anon_key},
            timeout=10,
        )
        assert r.status_code == 200, \
            f"user1 should be able to download their document after state change, got {r.status_code}: {r.text}"

        # 5. user1 tries to update the order_document record — should fail (order in 'ordered', not 'initial')
        r = req.patch(
            f"{supabase_url}/rest/v1/order_document?id=eq.{doc_id}",
            headers={**api_headers(user1_token), "Prefer": "return=representation"},
            json={"tag": "updated_invoice"},
            timeout=10,
        )
        updated = r.status_code in (200, 204) and (r.text.strip() not in ("", "[]"))
        assert not updated, \
            f"user1 should NOT be able to update order_document when order is 'ordered', got {r.status_code}: {r.text}"

    finally:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            if order_id:
                cur.execute(f'DELETE FROM "order" WHERE id = {order_id};')
        conn.close()
        if storage_path and service_role_key:
            req.delete(
                f"{supabase_url}/storage/v1/object/{bucket}",
                headers={"Authorization": f"Bearer {service_role_key}", "apikey": anon_key,
                         "Content-Type": "application/json"},
                json={"prefixes": [storage_path]},
                timeout=10,
            )


@pytest.mark.integration
def test_anon_can_read_category():
    """anon role can SELECT from category (has _anon read RLS policy)."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    category_id = None

    with conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO category (name, slug) VALUES ('_test_anon_read', '_test-anon-read') RETURNING id;"
            )
            category_id = cur.fetchone()[0]

            cur.execute("BEGIN;")
            try:
                cur.execute("SET LOCAL ROLE anon;")
                cur.execute(f'SELECT id FROM "category" WHERE id = {category_id};')
                assert cur.fetchone() is not None, "anon role should be able to read category rows"
            finally:
                cur.execute("ROLLBACK;")
        finally:
            if category_id:
                cur.execute(f"DELETE FROM category WHERE id = {category_id};")


@pytest.mark.integration
def test_anon_cannot_write_category():
    """anon role cannot INSERT into category (no write RLS policy for anon)."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    with conn.cursor() as cur:
        blocked = False
        cur.execute("BEGIN;")
        try:
            cur.execute("SET LOCAL ROLE anon;")
            cur.execute(
                "INSERT INTO category (name, slug) VALUES ('_anon_write_attempt', '_anon-write') RETURNING id;"
            )
            if cur.fetchone() is None:
                blocked = True
        except psycopg2.Error:
            blocked = True
        finally:
            cur.execute("ROLLBACK;")
        assert blocked, "anon role should NOT be able to insert into category"


@pytest.mark.integration
def test_anon_cannot_read_customer():
    """anon role cannot SELECT from customer (only has allow_all_authenticated policy)."""
    load_dotenv("test-app/backend/.env")
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found, skipping integration test.")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute("BEGIN;")
        try:
            cur.execute("SET LOCAL ROLE anon;")
            cur.execute('SELECT id FROM "customer" LIMIT 1;')
            assert cur.fetchone() is None, "anon role should NOT be able to read customer rows"
        finally:
            cur.execute("ROLLBACK;")
