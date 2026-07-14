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


def test_async_rule_generates_one_trigger_per_state():
    """A rule with several on_change_in_state_* entries must generate distinct
    trigger names per state — a shared name would let the last DROP+CREATE win
    and silently disable the async rule in the other states."""
    from unibizkit.generators.backend.context import Context
    from unibizkit.generators.backend import rules as rules_gen

    concepts = [{
        "name": "order",
        "plural_name": "orders",
        "fields": [{"name": "subtotal", "type": "decimal"}],
    }]
    ctx = Context(
        concepts=concepts,
        concept_map={c["name"]: c for c in concepts},
        security_config={},
        business_schema={},
        workflow_config={},
        system_config={},
        deployment_config={},
        seed_data_config={},
        rules_config={"rules": [{
            "concept": "order",
            "name": "order-compute-totals",
            "feel_expr": "{ grand_total: db.order.subtotal }",
            "action": "update",
            "when": [],
            "when_async": ["on_change_in_state_initial", "on_change_in_state_checkout"],
        }]},
        validations_config={"validations": []},
    )

    sql = "\n".join(rules_gen.generate_async_rule_execution_sql(ctx))
    assert '"02_enqueue_rule_order_compute_totals_initial_trigger"' in sql
    assert '"02_enqueue_rule_order_compute_totals_checkout_trigger"' in sql
    assert sql.count("CREATE TRIGGER") == 2


def _task_assignment_fixture():
    workflow = {
        "name": "order_workflow",
        "concepts": "order",
        "states": [
            {"name": "initial", "owners": ["user", "admin"], "assigners": [], "retain_task_owner": False},
            {"name": "ordered", "owners": ["admin"], "assigners": ["admin"], "retain_task_owner": False},
            {"name": "delivered", "owners": ["admin"], "assigners": ["admin"], "retain_task_owner": True},
        ],
    }
    concepts = [{
        "name": "order",
        "plural_name": "orders",
        "documents": {"enabled": False},
        "fields": [
            {"name": "notes", "type": "string", "required": False},
            {"name": "state", "type": "string", "required": True},
            {"name": "state_task_owner", "type": "string", "required": False},
        ],
    }]
    security_config = {
        "authentication_required": True,
        "roles": [{"name": "user"}, {"name": "admin"}],
        "users": [{"email": "admin@test.com", "password": "x", "roles": ["admin"]}],
        "registration": {"allow": False, "role": "user"},
        "sso": {"enabled": False, "role_claim": "roles", "default_role": "user"},
        "_profile_concepts": [],
        "_acl": {"order": {"_main": {"admin": "write", "user": "write"}, "_fields": {}}},
    }
    workflow_config = {"workflow_rules": [workflow], "_concept_workflow": {"order": workflow}}
    return concepts, security_config, workflow_config


def test_task_owner_security_trigger_sql():
    """The per-concept security trigger must gate state_task_owner changes on
    the state's assigners, and exempt assignment-only updates from the owners
    check (jsonb comparison also ignores the trigger-bumped _updated_at)."""
    from unibizkit.generators.backend.schema_parts.security import generate_security_policies

    concepts, security_config, workflow_config = _task_assignment_fixture()
    sql = "\n".join(generate_security_policies(
        concepts, {c["name"]: c for c in concepts}, security_config, workflow_config
    ))

    # Empty assigners: nobody can assign in 'initial'.
    assert "Task assignment is not allowed in state initial" in sql
    # Non-empty assigners: role check in 'ordered'.
    assert "Insufficient privilege to assign task in state ordered" in sql
    assert "user_roles ?| array['admin']" in sql
    # Owners check ignores assignment-only updates and the bumped timestamp.
    assert "(to_jsonb(NEW) - 'state_task_owner' - '_updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'state_task_owner' - '_updated_at')" in sql


def test_user_directory_and_email_trigger_sql():
    from unibizkit.generators.backend.schema_parts.workflow_tasks import (
        generate_user_directory, generate_task_assignment_email_triggers,
        generate_workflow_tasks_view,
    )

    _, security_config, workflow_config = _task_assignment_fixture()

    directory_sql = "\n".join(generate_user_directory(workflow_config, security_config))
    assert 'CREATE TABLE "user_directory"' in directory_sql
    assert 'USING GIN ("roles")' in directory_sql

    email_sql = "\n".join(generate_task_assignment_email_triggers(workflow_config, security_config))
    assert "task-assigned-email" in email_sql
    assert '"02_notify_task_assignment_trigger" ON "order"' in email_sql

    # workflow_tasks view: caller RLS, per-state assigners as text[], stable ids.
    view_sql = "\n".join(generate_workflow_tasks_view(workflow_config, security_config))
    assert 'CREATE VIEW "workflow_tasks" WITH (security_invoker = true)' in view_sql
    assert "'order' || '-' || t.\"id\"::text" in view_sql
    assert "WHEN 'ordered' THEN ARRAY['admin']::text[]" in view_sql
    assert "WHEN 'initial' THEN ARRAY[]::text[]" in view_sql

    # Nothing is generated without workflows or without authentication.
    assert generate_user_directory({"_concept_workflow": {}}, security_config) == []
    no_auth = dict(security_config, authentication_required=False)
    assert generate_task_assignment_email_triggers(workflow_config, no_auth) == []
    assert generate_workflow_tasks_view(workflow_config, no_auth) == []


def test_workflow_transition_handles_retain_task_owner():
    """The transition function must clear state_task_owner when entering a
    state, unless the target state sets retain_task_owner."""
    from unibizkit.generators.backend.context import Context
    from unibizkit.generators.backend import rules as rules_gen

    concepts, security_config, workflow_config = _task_assignment_fixture()
    ctx = Context(
        concepts=concepts,
        concept_map={c["name"]: c for c in concepts},
        security_config=security_config,
        business_schema={},
        workflow_config=workflow_config,
        system_config={},
        deployment_config={},
        seed_data_config={},
        rules_config={"rules": []},
        validations_config={"validations": []},
    )

    generated = rules_gen.generate_supabase_rules(ctx)
    assert "workflow-transition" in generated
    transition_ts = generated["workflow-transition"]["index.ts"]
    assert "retain_task_owner" in transition_ts
    assert "update.state_task_owner = null" in transition_ts

    assert "task-assigned-email" in generated
    email_ts = generated["task-assigned-email"]["index.ts"]
    # Built-in SMTP client: the edge runtime cannot load remote deno.land modules
    assert "sendSmtpMail" in email_ts
    assert "MAIL FROM" in email_ts
    assert "AUTH LOGIN" not in email_ts
    assert "SMTP_USER" not in email_ts
    assert "SMTP_PASS" not in email_ts
    assert "https://deno.land" not in email_ts
    assert "state_task_owner" in email_ts
    assert "#/admin/" in email_ts


@pytest.mark.integration
def test_workflow_task_assignment_permissions():
    """
    Task assignment (state_task_owner) permissions:
    1. In 'initial' (assigners: []) nobody can assign, not even admin.
    2. In 'ordered' (assigners: ['admin']) user1 cannot assign.
    3. In 'ordered' admin can assign, and the seeded user_directory exists.
    """
    env_path = Path("test-app/backend/.env")
    if not env_path.exists():
        pytest.skip("test-app/backend/.env not found. Run generate first.")

    load_dotenv(env_path)
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("No DB_URL found in .env")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    def set_jwt(cur, user_id, email, roles):
        cur.execute("SET LOCAL ROLE authenticated")
        claims = json.dumps({"sub": str(user_id), "email": email, "app_metadata": {"roles": roles}})
        cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (claims,))

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email FROM auth.users WHERE email IN ('user1@test.com', 'admin@test.com')")
            users = dict((email, uid) for uid, email in cur.fetchall())
            user1_id = users.get('user1@test.com')
            admin_id = users.get('admin@test.com')
            if not user1_id or not admin_id:
                pytest.skip("Required test users (user1@test.com, admin@test.com) not found in auth.users")

            # Discovery cache populated (seeded, then upgraded to 'login' by the
            # access token hook once a user authenticates)
            cur.execute("SELECT source FROM user_directory WHERE email = 'admin@test.com'")
            row = cur.fetchone()
            assert row and row[0] in ('seed', 'login')

            # Order in 'initial' created by user1
            cur.execute("BEGIN;")
            set_jwt(cur, user1_id, 'user1@test.com', ["user"])
            cur.execute("""
                INSERT INTO "order" (
                    order_date, shipping_address_street, shipping_address_city,
                    shipping_address_province, shipping_address_country, state
                )
                VALUES (CURRENT_TIMESTAMP, 'Assign Addr', 'Bilbao', 'Bizkaia', 'Spain', 'initial')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            cur.execute("COMMIT;")

            # 1. 'initial' has no assigners: even admin is rejected
            cur.execute("BEGIN;")
            set_jwt(cur, admin_id, 'admin@test.com', ["admin"])
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "UPDATE \"order\" SET state_task_owner = 'admin@test.com' WHERE id = %s",
                    (order_id,),
                )
            cur.execute("ROLLBACK;")

            # Move to 'ordered' through the edge function
            returncode, result = _call_edge_function_script(
                "user1@test.com",
                "workflow-transition",
                {"concept": "order", "id": order_id, "to_state": "ordered"},
            )
            assert returncode == 0, f"user1 should move order to 'ordered': {result}"

            # 2. user1 is not an assigner of 'ordered'
            cur.execute("BEGIN;")
            set_jwt(cur, user1_id, 'user1@test.com', ["user"])
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "UPDATE \"order\" SET state_task_owner = 'user1@test.com' WHERE id = %s",
                    (order_id,),
                )
            cur.execute("ROLLBACK;")

            # 3. admin is an assigner of 'ordered'
            cur.execute("BEGIN;")
            set_jwt(cur, admin_id, 'admin@test.com', ["admin"])
            cur.execute(
                "UPDATE \"order\" SET state_task_owner = 'user1@test.com' WHERE id = %s",
                (order_id,),
            )
            cur.execute("COMMIT;")
            cur.execute("SELECT state_task_owner FROM \"order\" WHERE id = %s", (order_id,))
            assert cur.fetchone()[0] == 'user1@test.com'

            # The workflow_tasks view exposes the row with the state's assigners
            cur.execute("BEGIN;")
            set_jwt(cur, admin_id, 'admin@test.com', ["admin"])
            cur.execute(
                "SELECT concept, state, state_task_owner, assigners FROM workflow_tasks "
                "WHERE concept = 'order' AND record_id = %s",
                (order_id,),
            )
            concept, state, task_owner, assigners = cur.fetchone()
            assert (concept, state, task_owner) == ('order', 'ordered', 'user1@test.com')
            assert assigners == ['admin']
            cur.execute("ROLLBACK;")

            # 4. Transition clears the task owner ('accepted' has no retain_task_owner)
            returncode, result = _call_edge_function_script(
                "admin@test.com",
                "workflow-transition",
                {"concept": "order", "id": order_id, "to_state": "accepted"},
            )
            assert returncode == 0, f"admin should move order to 'accepted': {result}"
            cur.execute("SELECT state, state_task_owner FROM \"order\" WHERE id = %s", (order_id,))
            state, task_owner = cur.fetchone()
            assert state == 'accepted'
            assert task_owner is None
    finally:
        conn.close()


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
                INSERT INTO "order" (
                    order_date,
                    shipping_address_street,
                    shipping_address_city,
                    shipping_address_province,
                    shipping_address_country,
                    state
                )
                VALUES (CURRENT_TIMESTAMP, 'Initial Addr', 'Bilbao', 'Bizkaia', 'Spain', 'initial')
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
