import pytest
import os
import psycopg2
import json
import subprocess
from dotenv import load_dotenv
from pathlib import Path
import sys


def _call_edge_function_script(email, function_name, payload=None):
    script = Path("test-app/bin/dev-supabase-call-edge-function.py")
    assert script.exists(), "dev-supabase-call-edge-function.py must be generated"
    args = [sys.executable, str(script), email, function_name]
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


@pytest.mark.integration
def test_workflow_state_permissions():
    """
    Test workflow state permissions:
    1. user1 can create order in 'initial' state.
    2. user1 can move order to 'ordered' state.
    3. once in 'ordered', user1 (who is not an owner of 'ordered') cannot edit it.
    4. admin (who is owner of 'ordered') can edit it.
    """
    # Load env from test-app
    env_path = Path("test-app/backend/.env")
    if not env_path.exists():
        pytest.skip("test-app/backend/.env not found. Run generate first.")
    
    load_dotenv(env_path)
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found in .env")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    
    try:
        with conn.cursor() as cur:
            # 0. Setup: Get user IDs
            cur.execute("SELECT id, email FROM auth.users WHERE email IN ('user1@test.com', 'admin@test.com')")
            users = dict((email, uid) for uid, email in cur.fetchall())
            user1_id = users.get('user1@test.com')
            admin_id = users.get('admin@test.com')
            
            if not user1_id or not admin_id:
                pytest.skip("Required test users (user1@test.com, admin@test.com) not found in auth.users")

            # Get a customer ID for the order
            cur.execute('SELECT id FROM "customer" LIMIT 1')
            customer_id = cur.fetchone()[0]

            # --- STEP 1: As user1, create order in 'initial' ---
            cur.execute("BEGIN;")
            cur.execute("SET LOCAL ROLE authenticated")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{{\"sub\": \"{user1_id}\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}', true)")
            
            cur.execute(f"""
                INSERT INTO "order" (order_date, shipping_address_street, state)
                VALUES (CURRENT_TIMESTAMP, 'Initial Addr', 'initial')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute("COMMIT;")

            # --- STEP 2: As user1, move order to 'ordered' through workflow-transition ---
            returncode, result = _call_edge_function_script(
                "user1@test.com",
                "workflow-transition",
                {"concept": "order", "id": order_id, "to_state": "ordered"},
            )
            assert returncode == 0, f"user1 should move order to 'ordered': {result}"
            assert result["status"] == 200

            # --- STEP 3: As user1, try to edit 'shipping_address_street' in 'ordered' state ---
            # user1 is NOT owner of 'ordered' state, so RLS should block this.
            cur.execute("BEGIN;")
            cur.execute("SET LOCAL ROLE authenticated")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{{\"sub\": \"{user1_id}\", \"app_metadata\": {{\"roles\": [\"user\"]}}}}', true)")
            
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f"UPDATE \"order\" SET shipping_address_street = 'User1 Hack Attempt' WHERE id = {order_id}")
            
            cur.execute("ROLLBACK;")

            # --- STEP 4: As admin, edit 'shipping_address_street' in 'ordered' state ---
            # admin IS owner of 'ordered' state.
            cur.execute("BEGIN;")
            cur.execute("SET LOCAL ROLE authenticated")
            cur.execute(f"SELECT set_config('request.jwt.claims', '{{\"sub\": \"{admin_id}\", \"app_metadata\": {{\"roles\": [\"admin\"]}}}}', true)")
            
            cur.execute(f"UPDATE \"order\" SET shipping_address_street = 'Admin Correction' WHERE id = {order_id}")
            cur.execute("COMMIT;")
            
            # Verify update worked
            cur.execute(f"SELECT shipping_address_street FROM \"order\" WHERE id = {order_id}")
            assert cur.fetchone()[0] == 'Admin Correction'

    finally:
        conn.close()
