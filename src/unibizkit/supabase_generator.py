"""
Supabase Schema Generation Module

Generates PostgreSQL database schema for Supabase from business concept definitions.
"""

from typing import Dict, Any, List, Tuple
from .schema_loader import SchemaLoader
import logging
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)

class SupabaseGenerator:
    def __init__(self, schema_loader: SchemaLoader):
        """
        Initialize the Supabase generator.
        
        Args:
            schema_loader: SchemaLoader instance with loaded business schema
        """
        self.schema_loader = schema_loader
        self.concepts = schema_loader.get_all_concepts()
        self.concept_map = {concept["name"]: concept for concept in self.concepts}
    
    def generate_supabase_config(self) -> str:
        """
        Generate a complete supabase/config.toml for local development.
        Ports are shifted to 55xxx to avoid conflicts with other Supabase instances.
        """
        system_config = getattr(self.schema_loader, 'system_config', None) or {}
        smtp = system_config.get('smtp', {})
        smtp_host = smtp.get('host', '127.0.0.1')
        # Supabase runs in Docker; remap loopback addresses to the Docker bridge
        # gateway so the container can reach services on the host.
        if smtp_host in ('127.0.0.1', 'localhost'):
            smtp_host = '172.17.0.1'
        smtp_port = smtp.get('port', 25)
        smtp_from = smtp.get('from_email', 'noreply@localhost')
        smtp_user = smtp.get('user') or 'mock'
        smtp_pass = smtp.get('password') or 'mock'
        base_url = system_config.get('base_url', 'http://localhost:3000')

        registration = self.schema_loader.security_config['registration']
        allow_registration = registration['allow']
        enable_signup = 'true' if allow_registration else 'false'

        app_name = self.schema_loader.business_schema.get('name', 'app')
        import re
        project_id = re.sub(r'[^a-z0-9]+', '_', app_name.lower()).strip('_')

        return f"""# For detailed configuration reference documentation, visit:
# https://supabase.com/docs/guides/local-development/cli/config
project_id = "{project_id}"

[api]
enabled = true
port = 55321
schemas = ["public", "graphql_public"]
extra_search_path = ["public", "extensions"]
max_rows = 1000

[api.tls]
enabled = false

[db]
port = 55322
shadow_port = 55320
health_timeout = "2m"
major_version = 17

[db.pooler]
enabled = false
port = 55329
pool_mode = "transaction"
default_pool_size = 20
max_client_conn = 100

[db.migrations]
enabled = true
schema_paths = []

[db.seed]
enabled = true
sql_paths = ["./seed.sql"]

[db.network_restrictions]
enabled = false
allowed_cidrs = ["0.0.0.0/0"]
allowed_cidrs_v6 = ["::/0"]

[realtime]
enabled = true

[studio]
enabled = true
port = 55323
api_url = "http://127.0.0.1"
openai_api_key = "env(OPENAI_API_KEY)"

[inbucket]
enabled = false
port = 55324

[storage]
enabled = true
file_size_limit = "50MiB"

[storage.s3_protocol]
enabled = true

[storage.analytics]
enabled = false
max_namespaces = 5
max_tables = 10
max_catalogs = 2

[storage.vector]
enabled = false
max_buckets = 10
max_indexes = 5

[auth]
enabled = true
site_url = "{base_url}"
additional_redirect_urls = ["https://127.0.0.1:3000"]
jwt_expiry = 3600
enable_refresh_token_rotation = true
refresh_token_reuse_interval = 10
enable_signup = {enable_signup}
enable_anonymous_sign_ins = false
enable_manual_linking = false
minimum_password_length = 6
password_requirements = ""

[auth.rate_limit]
email_sent = 100
sms_sent = 30
anonymous_users = 30
token_refresh = 150
sign_in_sign_ups = 30
token_verifications = 30
web3 = 30

[auth.email]
enable_signup = {enable_signup}
double_confirm_changes = false
enable_confirmations = true
secure_password_change = false
max_frequency = "1s"
otp_length = 6
otp_expiry = 3600

[auth.sms]
enable_signup = true
enable_confirmations = true
template = "Your code is {{{{ .Code }}}}"
max_frequency = "5s"

[auth.sms.twilio]
enabled = false
account_sid = ""
message_service_sid = ""
auth_token = "env(SUPABASE_AUTH_SMS_TWILIO_AUTH_TOKEN)"

[auth.mfa]
max_enrolled_factors = 10

[auth.mfa.totp]
enroll_enabled = false
verify_enabled = false

[auth.mfa.phone]
enroll_enabled = false
verify_enabled = false
otp_length = 6
template = "Your code is {{{{ .Code }}}}"
max_frequency = "5s"

[auth.external.apple]
enabled = false
client_id = ""
secret = "env(SUPABASE_AUTH_EXTERNAL_APPLE_SECRET)"
redirect_uri = ""
url = ""
skip_nonce_check = false
email_optional = false

[auth.web3.solana]
enabled = false

[auth.third_party.firebase]
enabled = false

[auth.third_party.auth0]
enabled = false

[auth.third_party.aws_cognito]
enabled = false

[auth.third_party.clerk]
enabled = false

[auth.oauth_server]
enabled = false
authorization_url_path = "/oauth/consent"
allow_dynamic_registration = false

[edge_runtime]
enabled = true
policy = "per_worker"
inspector_port = 8083
deno_version = 2

[analytics]
enabled = true
port = 55327
backend = "postgres"

[experimental]
orioledb_version = ""
s3_host = "env(S3_HOST)"
s3_region = "env(S3_REGION)"
s3_access_key = "env(S3_ACCESS_KEY)"
s3_secret_key = "env(S3_SECRET_KEY)"

[auth.email.smtp]
enabled = true
host = "{smtp_host}"
port = {smtp_port}
admin_email = "{smtp_from}"
sender_name = "App"
user = "{smtp_user}"
pass = "{smtp_pass}"
"""

    def generate_sql_schema(self) -> str:
        """
        Generate complete SQL schema for Supabase.
        
        Returns:
            SQL statements as a string
        """
        sql_parts = []

        # Ensure pgcrypto is available for password hashing
        sql_parts.append("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

        # Add generic updated_at function
        sql_parts.append("""
CREATE OR REPLACE FUNCTION update_updated_at_column() 
RETURNS TRIGGER AS $$
BEGIN
    NEW."_updated_at" = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")
        
        # Generate tables for each concept
        for concept in self.concepts:
            table_sql = self._generate_table_sql(concept)
            sql_parts.append(table_sql)
        
        # Generate join tables for many-to-many relationships
        join_tables = self._generate_join_tables()
        sql_parts.extend(join_tables)
        
        # Generate foreign key constraints
        fk_constraints = self._generate_foreign_key_constraints()
        sql_parts.extend(fk_constraints)

        # Generate document tables
        document_tables = self._generate_document_tables()
        sql_parts.extend(document_tables)

        # Generate presentation triggers
        presentation_triggers = self._generate_presentation_triggers()
        sql_parts.extend(presentation_triggers)
        
        # Generate Security Policies (RLS)
        if self.schema_loader.security_config["authentication_required"]:
            security_policies = self._generate_security_policies()
            sql_parts.extend(security_policies)
        
        return '\n\n'.join(sql_parts)

    def _generate_security_policies(self) -> List[str]:
        """
        Generate Row Level Security (RLS) policies.
        """
        policies = []

        # 1. Trigger to set default roles for new users
        registration = self.schema_loader.security_config["registration"]
        if registration["allow"]:
            default_role = registration["role"]
            policies.append(f"""
-- Trigger to set default roles for new users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  -- We set the role in app_metadata
  UPDATE auth.users
  SET raw_app_meta_data = coalesce(raw_app_meta_data, '{{}}'::jsonb) || 
    jsonb_build_object('roles', array['{default_role}'])
  WHERE id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Check if trigger exists and recreate it
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
""")
        
        _acl = self.schema_loader.security_config["_acl"]
        roles = self.schema_loader.security_config["roles"]
        all_role_names = set(r["name"] for r in roles)
        
        # Calculate join table names cleanly.
        join_tables = []
        for concept in self.concepts:
            for field in concept["fields"]:
                if field["type"] == "relation_to_many":
                    target_name = field["target"]
                    target_concept = self.concept_map.get(target_name)
                    if not target_concept: continue
                    
                    is_one_to_many = False
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                             is_one_to_many = True
                             break
                    
                    if not is_one_to_many:
                        t1, t2 = concept["name"], target_name
                        jt = f"{min(t1, t2)}_{max(t1, t2)}"
                        if jt not in join_tables:
                            join_tables.append(jt)
        
        all_tables = [c["name"] for c in self.concepts] + join_tables

        # Build a map of concept -> workflow rules
        concept_workflows = self.schema_loader.business_schema["_concept_workflow"]

        for table in all_tables:
            policies.append(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            
            concept_acl = _acl.get(table)
            workflow = concept_workflows.get(table)
            
            if not concept_acl:
                # Fallback: if no rules for this concept (or if it's a join table), allow all authenticated
                policies.append(f"""
CREATE POLICY "allow_all_authenticated_{table}" ON "{table}"
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);
""")
                continue

            # Field and Workflow security checks (trigger based)
            concept = self.concept_map.get(table)
            main_rules = concept_acl["_main"]
            if concept:
                trigger_checks = []
                
                # 1. Workflow state validation
                if workflow:
                    # Determine which roles own which states
                    for state in workflow["states"]:
                        state_name = state["name"]
                        owners = state["owners"]
                        roles_json_array = ", ".join(f"'{r}'" for r in owners)
                        
                        # If row is currently in this state, check if user has permission to edit/delete
                        trigger_checks.append(f"""
    IF (TG_OP IN ('UPDATE', 'DELETE') AND OLD."state" = '{state_name}') THEN
        IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Insufficient privilege for state {state_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;""")
                        
                        # For inserts, check if user has permission for the initial state
                        trigger_checks.append(f"""
    IF (TG_OP = 'INSERT' AND NEW."state" = '{state_name}') THEN
        IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Insufficient privilege for state {state_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;""")

                # 2. Protect system timestamps
                trigger_checks.append("""
    -- System timestamps are immutable / system-controlled
    IF (TG_OP = 'INSERT') THEN
        NEW."_created_at" := CURRENT_TIMESTAMP;
        NEW."_updated_at" := CURRENT_TIMESTAMP;
    ELSIF (TG_OP = 'UPDATE' AND NEW."_created_at" IS DISTINCT FROM OLD."_created_at") THEN
        RAISE EXCEPTION 'Permission denied: _created_at is immutable' USING ERRCODE = 'insufficient_privilege';
    END IF;""")

                # 3. Field-level write restrictions
                has_security_owner_id = any(f["name"] == "security_owner_id" for f in concept["fields"])
                if has_security_owner_id:
                    trigger_checks.append("""
    -- security_owner_id is immutable after insert
    IF (TG_OP = 'UPDATE' AND NEW."security_owner_id" IS DISTINCT FROM OLD."security_owner_id") THEN
        RAISE EXCEPTION 'Permission denied: security_owner_id is immutable' USING ERRCODE = 'insufficient_privilege';
    END IF;""")

                for field in concept["fields"]:
                    field_name = field["name"]
                    if field_name == "security_owner_id":
                        continue
                    field_rules = concept_acl["_fields"].get(field_name, {})

                    allowed_roles = []
                    for role in all_role_names:
                        access = field_rules.get(role, main_rules.get(role, "none"))
                        if access in ("write", "owner_write"):
                            allowed_roles.append(role)

                    # If this field has limited writers
                    if allowed_roles and set(allowed_roles) != all_role_names:
                        roles_json_array = ", ".join(f"'{r}'" for r in allowed_roles)
                        check = f"""
    -- Check field '{field_name}'
    IF (TG_OP = 'UPDATE' AND NEW."{field_name}" IS DISTINCT FROM OLD."{field_name}") OR (TG_OP = 'INSERT' AND NEW."{field_name}" IS NOT NULL) THEN
        IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Permission denied for field {field_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;"""
                        trigger_checks.append(check)
                
                if trigger_checks:
                    trigger_name = f"{table}_security"
                    trigger_func = f"""
CREATE OR REPLACE FUNCTION "{trigger_name}_func"()
RETURNS TRIGGER AS $$
DECLARE
    user_roles jsonb := coalesce(auth.jwt() -> 'app_metadata' -> 'roles', '[]'::jsonb);
BEGIN
    -- Bypass trigger for system operations (like seeding data directly)
    IF current_setting('request.jwt.claims', true) IS NULL OR current_setting('request.jwt.claims', true) = '' THEN
        IF (TG_OP = 'DELETE') THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;
{''.join(trigger_checks)}
    IF (TG_OP = 'DELETE') THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS "{trigger_name}" ON "{table}";
CREATE TRIGGER "{trigger_name}"
BEFORE INSERT OR UPDATE OR DELETE ON "{table}"
FOR EACH ROW
EXECUTE FUNCTION "{trigger_name}_func"();
"""
                    policies.append(trigger_func)

            # Generate table-level RLS policies
            # Determine max access for each role on this table
            role_table_access = {} # role -> max_access
            for role in all_role_names:
                role_table_access[role] = main_rules.get(role, "none")
                
            for field_name, field_rules in concept_acl["_fields"].items():
                for role, access in field_rules.items():
                    current = role_table_access.get(role, "none")
                    if access == "write" or current == "write":
                        role_table_access[role] = "write"
                    elif access == "owner_write" and current not in ("write", "owner_write"):
                        role_table_access[role] = "owner_write"
                    elif access == "read" and current == "none":
                        role_table_access[role] = "read"

            for role, access in role_table_access.items():
                role_condition = f"auth.jwt() -> 'app_metadata' -> 'roles' ? '{role}'"
                
                if access == "read":
                    policies.append(f"""
CREATE POLICY "{role}_read_{table}" ON "{table}"
FOR SELECT
TO authenticated
USING ({role_condition});
""")
                elif access == "write":
                    policies.append(f"""
CREATE POLICY "{role}_select_{table}" ON "{table}"
FOR SELECT
TO authenticated
USING ({role_condition});
""")
                    policies.append(f"""
CREATE POLICY "{role}_insert_{table}" ON "{table}"
FOR INSERT
TO authenticated
WITH CHECK ({role_condition});
""")
                    policies.append(f"""
CREATE POLICY "{role}_update_{table}" ON "{table}"
FOR UPDATE
TO authenticated
USING ({role_condition})
WITH CHECK ({role_condition});
""")
                    policies.append(f"""
CREATE POLICY "{role}_delete_{table}" ON "{table}"
FOR DELETE
TO authenticated
USING ({role_condition});
""")
                elif access == "owner_write":
                    policies.append(f"""
CREATE POLICY "{role}_owner_select_{table}" ON "{table}"
FOR SELECT
TO authenticated
USING ({role_condition} AND "security_owner_id" = auth.uid()::text);
""")
                    policies.append(f"""
CREATE POLICY "{role}_owner_insert_{table}" ON "{table}"
FOR INSERT
TO authenticated
WITH CHECK ({role_condition} AND "security_owner_id" = auth.uid()::text);
""")
                    policies.append(f"""
CREATE POLICY "{role}_owner_update_{table}" ON "{table}"
FOR UPDATE
TO authenticated
USING ({role_condition} AND "security_owner_id" = auth.uid()::text)
WITH CHECK ({role_condition} AND "security_owner_id" = auth.uid()::text);
""")
                    policies.append(f"""
CREATE POLICY "{role}_owner_delete_{table}" ON "{table}"
FOR DELETE
TO authenticated
USING ({role_condition} AND "security_owner_id" = auth.uid()::text);
""")

        # RLS for document tables (based on _documents virtual field ACL)
        for concept in self.concepts:
            if not concept["documents"]["enabled"]:
                continue

            owner_name = concept["name"]
            doc_table = f"{owner_name}_document"
            policies.append(f'ALTER TABLE "{doc_table}" ENABLE ROW LEVEL SECURITY;')

            concept_acl = _acl.get(owner_name)
            if not concept_acl:
                policies.append(f"""
CREATE POLICY "allow_all_authenticated_{doc_table}" ON "{doc_table}"
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);
""")
                continue

            # Use _documents field ACL, falling back to concept main ACL
            docs_field_acl = concept_acl["_fields"].get("_documents", {})
            main_acl = concept_acl["_main"]

            fk_col = f"{owner_name}_id"
            for role in all_role_names:
                access = docs_field_acl.get(role) or main_acl.get(role, "none")
                if access == "none":
                    continue
                role_condition = f"auth.jwt() -> 'app_metadata' -> 'roles' ? '{role}'"

                if access == "owner_write":
                    owner_condition = (
                        f'EXISTS (SELECT 1 FROM "{owner_name}" '
                        f'WHERE "{owner_name}"."id" = "{doc_table}"."{fk_col}" '
                        f'AND "{owner_name}"."security_owner_id" = auth.uid()::text)'
                    )
                    full_using = f"{role_condition} AND {owner_condition}"
                    policies.append(f"""
CREATE POLICY "{role}_select_{doc_table}" ON "{doc_table}"
FOR SELECT
TO authenticated
USING ({full_using});
""")
                    policies.append(f"""
CREATE POLICY "{role}_insert_{doc_table}" ON "{doc_table}"
FOR INSERT
TO authenticated
WITH CHECK ({full_using});
""")
                    policies.append(f"""
CREATE POLICY "{role}_update_{doc_table}" ON "{doc_table}"
FOR UPDATE
TO authenticated
USING ({full_using})
WITH CHECK ({full_using});
""")
                    policies.append(f"""
CREATE POLICY "{role}_delete_{doc_table}" ON "{doc_table}"
FOR DELETE
TO authenticated
USING ({full_using});
""")
                elif access == "write":
                    policies.append(f"""
CREATE POLICY "{role}_select_{doc_table}" ON "{doc_table}"
FOR SELECT
TO authenticated
USING ({role_condition});
""")
                    policies.append(f"""
CREATE POLICY "{role}_insert_{doc_table}" ON "{doc_table}"
FOR INSERT
TO authenticated
WITH CHECK ({role_condition});
""")
                    policies.append(f"""
CREATE POLICY "{role}_update_{doc_table}" ON "{doc_table}"
FOR UPDATE
TO authenticated
USING ({role_condition})
WITH CHECK ({role_condition});
""")
                    policies.append(f"""
CREATE POLICY "{role}_delete_{doc_table}" ON "{doc_table}"
FOR DELETE
TO authenticated
USING ({role_condition});
""")
                elif access == "read":
                    policies.append(f"""
CREATE POLICY "{role}_read_{doc_table}" ON "{doc_table}"
FOR SELECT
TO authenticated
USING ({role_condition});
""")

        return policies

    def _generate_document_tables(self) -> List[str]:
        """
        Generate SQL for document tables for concepts that have documents enabled.
        Also creates the Supabase Storage bucket for each concept's documents.
        """
        sql_parts = []
        for concept in self.concepts:
            docs = concept["documents"]
            if not docs["enabled"]:
                continue

            owner_name = concept["name"]
            table_name = f"{owner_name}_document"
            fk_col = f"{owner_name}_id"
            versioned = docs["versioned"]
            tags = docs["tags"]
            tags_sql = ", ".join(f"'{t}'" for t in tags)
            bucket_name = f"{owner_name}-documents"

            cols = [
                f'  "id" SERIAL PRIMARY KEY,',
                f'  "{fk_col}" INTEGER NOT NULL REFERENCES "{owner_name}"("id") ON DELETE CASCADE,',
                f'  "tag" TEXT NOT NULL,',
            ]
            if versioned:
                cols.append('  "version" INTEGER NOT NULL DEFAULT 1,')
                cols.append('  "is_current" BOOLEAN NOT NULL DEFAULT TRUE,')
            cols.append('  "storage_path" TEXT NOT NULL,')
            cols.append('  "_created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,')
            cols.append('  "_updated_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,')
            cols.append(f'  CONSTRAINT "{table_name}_tag_check" CHECK ("tag" IN ({tags_sql})),')
            if versioned:
                cols.append(f'  UNIQUE ("{fk_col}", "tag", "version")')
            else:
                cols.append(f'  UNIQUE ("{fk_col}", "tag")')

            create_sql = f'CREATE TABLE "{table_name}" (\n' + '\n'.join(cols) + '\n);'
            sql_parts.append(create_sql)

            # Trigger to update _updated_at
            sql_parts.append(f"""CREATE TRIGGER "{table_name}_updated_at_trigger"
  BEFORE UPDATE ON "{table_name}"
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();""")

            # Trigger to manage is_current for versioned documents
            if versioned:
                sql_parts.append(f"""CREATE OR REPLACE FUNCTION "{table_name}_manage_current_func"()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW."is_current" = TRUE THEN
    UPDATE "{table_name}"
    SET "is_current" = FALSE
    WHERE "{fk_col}" = NEW."{fk_col}"
      AND "tag" = NEW."tag"
      AND "id" != NEW."id";
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "{table_name}_manage_current_trigger"
  AFTER INSERT OR UPDATE OF "is_current" ON "{table_name}"
  FOR EACH ROW EXECUTE FUNCTION "{table_name}_manage_current_func"();""")

            # Build per-role storage policies based on the concept's document ACL
            _acl = self.schema_loader.security_config.get("_acl", {})
            concept_acl = _acl.get(owner_name, {})
            docs_field_acl = concept_acl.get("_fields", {}).get("_documents", {})
            main_acl = concept_acl.get("_main", {})
            all_roles = self.schema_loader.security_config.get("roles", [])

            # JOIN condition used by owner_write roles for SELECT/DELETE
            owner_read_join = (
                f'EXISTS (SELECT 1 FROM "{table_name}" od '
                f'JOIN "{owner_name}" o ON o.id = od."{fk_col}" '
                f'WHERE od."storage_path" = objects.name '
                f'AND o."security_owner_id" = auth.uid()::text)'
            )
            # JOIN condition used by owner_write roles for INSERT (path must start with an owned record ID)
            owner_insert_join = (
                f'EXISTS (SELECT 1 FROM "{owner_name}" o '
                f'WHERE o.id::text = (storage.foldername(objects.name))[1] '
                f'AND o."security_owner_id" = auth.uid()::text)'
            )

            bucket_clause = f"bucket_id = '{bucket_name}'"

            storage_sql = [f"""-- Storage bucket for {owner_name} documents
INSERT INTO storage.buckets (id, name, public)
VALUES ('{bucket_name}', '{bucket_name}', false)
ON CONFLICT (id) DO NOTHING;"""]

            for r in all_roles:
                role = r["name"]
                access = docs_field_acl.get(role) or main_acl.get(role, "none")
                if access == "none":
                    continue
                role_cond = f"auth.jwt() -> 'app_metadata' -> 'roles' ? '{role}'"

                # DROP existing per-role policies (idempotent re-runs)
                for op in ("select", "insert", "update", "delete"):
                    storage_sql.append(
                        f'DROP POLICY IF EXISTS "{role}_{op}_{bucket_name}" ON storage.objects;'
                    )

                if access == "owner_write":
                    storage_sql.append(f"""CREATE POLICY "{role}_select_{bucket_name}" ON storage.objects
  FOR SELECT TO authenticated
  USING ({bucket_clause} AND {role_cond} AND {owner_read_join});""")
                    storage_sql.append(f"""CREATE POLICY "{role}_insert_{bucket_name}" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK ({bucket_clause} AND {role_cond} AND {owner_insert_join});""")
                    storage_sql.append(f"""CREATE POLICY "{role}_update_{bucket_name}" ON storage.objects
  FOR UPDATE TO authenticated
  USING ({bucket_clause} AND {role_cond} AND {owner_read_join})
  WITH CHECK ({bucket_clause} AND {role_cond} AND {owner_insert_join});""")
                    storage_sql.append(f"""CREATE POLICY "{role}_delete_{bucket_name}" ON storage.objects
  FOR DELETE TO authenticated
  USING ({bucket_clause} AND {role_cond} AND {owner_read_join});""")
                elif access in ("write",):
                    storage_sql.append(f"""CREATE POLICY "{role}_select_{bucket_name}" ON storage.objects
  FOR SELECT TO authenticated
  USING ({bucket_clause} AND {role_cond});""")
                    storage_sql.append(f"""CREATE POLICY "{role}_insert_{bucket_name}" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK ({bucket_clause} AND {role_cond});""")
                    storage_sql.append(f"""CREATE POLICY "{role}_update_{bucket_name}" ON storage.objects
  FOR UPDATE TO authenticated
  USING ({bucket_clause} AND {role_cond})
  WITH CHECK ({bucket_clause} AND {role_cond});""")
                    storage_sql.append(f"""CREATE POLICY "{role}_delete_{bucket_name}" ON storage.objects
  FOR DELETE TO authenticated
  USING ({bucket_clause} AND {role_cond});""")
                elif access == "read":
                    storage_sql.append(f"""CREATE POLICY "{role}_select_{bucket_name}" ON storage.objects
  FOR SELECT TO authenticated
  USING ({bucket_clause} AND {role_cond});""")

            # Also drop the old blanket policy names from previous schema versions
            for old_op in ("read", "write", "update", "delete"):
                storage_sql.append(
                    f'DROP POLICY IF EXISTS "authenticated_{old_op}_{bucket_name}" ON storage.objects;'
                )

            sql_parts.append("\n".join(storage_sql))

        return sql_parts

    def _generate_table_sql(self, concept: Dict[str, Any]) -> str:
        """
        Generate SQL for a single concept table.
        
        Args:
            concept: Concept definition
            
        Returns:
            SQL CREATE TABLE statement
        """
        # Use enriched table name if available, fallback to name
        table_name = concept["name"]
        pk_name = "id"
        
        # Start with table creation
        sql_lines = [f'CREATE TABLE "{table_name}" (']
        sql_lines.append(f'  "{pk_name}" SERIAL PRIMARY KEY,')
        
        # Add fields
        for field in concept["fields"]:
            field_sql = self._generate_field_sql(field, concept)
            if field_sql:
                sql_lines.append(f"  {field_sql},")
        
        # Add id_presentation column based on enriched metadata
        presentation_mode = concept["_be_presentation_mode"]
        
        if presentation_mode == "generated_column":
            expr = concept["_be_presentation_expr"]
            sql_lines.append(f'  "id_presentation" TEXT GENERATED ALWAYS AS ({expr}) STORED,')
        elif presentation_mode == "trigger":
            sql_lines.append(f'  "id_presentation" TEXT,')
        
        # Add created_at and updated_at timestamps
        sql_lines.append('  "_created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,')
        sql_lines.append('  "_updated_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP')
        
        # Close table definition
        sql_lines.append(');')
        
        # Add check constraints
        checks = concept.get('checks', [])
        for i, check_expr in enumerate(checks):
            constraint_name = f"{table_name}_check_{i}"
            sql_lines.append(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" CHECK ({check_expr});')
        
        # Add trigger to update updated_at timestamp on row updates
        trigger_name = f"{table_name}_update_updated_at"
        sql_lines.append(f"""
CREATE TRIGGER "{trigger_name}" 
BEFORE UPDATE ON "{table_name}" 
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
"""
)

        # Add unique constraints
        unique_fields = [field for field in concept["fields"] if field["unique"]]
        for field in unique_fields:
            field_name = field["name"]
            constraint_name = f"{table_name}_{field_name}_unique"
            sql_lines.append(f'CREATE UNIQUE INDEX "{constraint_name}" ON "{table_name}" ("{field_name}");')
        
        return '\n'.join(sql_lines)
    
    def _generate_field_sql(self, field: Dict[str, Any], concept: Dict[str, Any]) -> str:

        """
        Generate SQL for a single field using enriched metadata.
        
        Args:
            field: Field definition
            concept: Concept definition (context)
            
        Returns:
            SQL field definition or empty string if field should be skipped
        """
        field_name = field["name"]
        
        # Use enriched SQL type
        sql_type = field["_be_sql_type"]
        
        if not sql_type:
            # Skip fields without SQL type (e.g., relation_to_many)
            return ""
        
        # Handle Calculated Fields
        if 'calculated' in field:
            expr = field["calculated"]
            sql_parts = [f'"{field_name}" {sql_type} GENERATED ALWAYS AS ({expr}) STORED']
            return ' '.join(sql_parts)

        field_parts = [f'"{field_name}" {sql_type}']
        
        # Use enriched Not Null constraint
        if field["_be_not_null"]:
            field_parts.append("NOT NULL")
        
        # Defaults
        if 'default' in field:
            default_value = field["default"]
            if isinstance(default_value, str):
                if default_value in ("auth.uid()", "auth.uid()::text"):
                    field_parts.append(f"DEFAULT {default_value}")
                else:
                    field_parts.append(f"DEFAULT '{default_value}'")
            elif isinstance(default_value, (int, float)):
                field_parts.append(f"DEFAULT {default_value}")
            elif isinstance(default_value, bool):
                field_parts.append(f"DEFAULT {str(default_value).upper()}")
        
        # Add enum constraints
        if field["type"] == "enum" and 'enum_values' in field:
            allowed_values = ', '.join([f"'{value}'" for value in field["enum_values"]])
            constraint_name = f"{field_name}_enum_check"
            field_parts.append(f"""CONSTRAINT "{constraint_name}" CHECK ("{field_name}" IN ({allowed_values}))""")
        
        return ' '.join(field_parts)
    
    def _generate_join_tables(self) -> List[str]:
        """
        Generate join tables for many-to-many relationships.
        
        Returns:
            List of SQL CREATE TABLE statements for join tables
        """
        join_tables = []
        
        for concept in self.concepts:
            # Handle new field-based relationships
            for field in concept["fields"]:
                if field["type"] == "relation_to_many":
                    target_concept_name = field["target"]
                    target_concept = self.concept_map.get(target_concept_name)
                    
                    if not target_concept:
                        continue
                        
                    # Check if target has a relation_to_one pointing back (which would make this 1:N)
                    is_one_to_many = False
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                             is_one_to_many = True
                             break
                    
                    if not is_one_to_many:
                        # It's Many-to-Many
                        table1 = concept["name"]
                        table2 = target_concept_name
                        join_table_name = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        # Only create the join table once
                        if join_table_name not in [jt.split('(')[0].strip() for jt in join_tables]:
                            sql = f"""
CREATE TABLE "{join_table_name}" (
  "{table1}_id" INTEGER NOT NULL,
  "{table2}_id" INTEGER NOT NULL,
  "_created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("{table1}_id", "{table2}_id"),
  FOREIGN KEY ("{table1}_id") REFERENCES "{table1}"("id") ON DELETE CASCADE,
  FOREIGN KEY ("{table2}_id") REFERENCES "{table2}"("id") ON DELETE CASCADE
);
"""
                            join_tables.append(sql)


        
        return join_tables
    
    def _generate_foreign_key_constraints(self) -> List[str]:
        """
        Generate foreign key constraints for relationships.
        
        Returns:
            List of SQL ALTER TABLE statements for foreign keys
        """
        fk_constraints = []
        
        for concept in self.concepts:
            table_name = concept["name"]
            
            # Handle new field-based relationships
            for field in concept["fields"]:
                if field["type"] == "relation_to_one":
                    target_table = field["target"]
                    field_name = field["name"] # The column name is the field name
                    
                    constraint_name = f"fk_{table_name}_{field_name}"
                    
                    # Add constraint only (column already created in table definition)
                    fk_sql = f"""
ALTER TABLE "{table_name}"
  ADD CONSTRAINT "{constraint_name}"
  FOREIGN KEY ("{field_name}") REFERENCES "{target_table}"("id");"""
                    fk_constraints.append(fk_sql)


        
        return fk_constraints

    def generate_sample_data_sql(self) -> str:
        """
        Generate SQL for inserting sample data.
        
        Returns:
            SQL INSERT statements as a string
        """
        sql_parts = []

        # Topological sort of concepts to ensure foreign key dependencies are met
        sorted_concepts = []
        visited = set()
        
        def visit(concept_name):
            if concept_name in visited:
                return
            
            concept = self.concept_map.get(concept_name)
            if not concept:
                return
                

            
            visited.add(concept_name)
            sorted_concepts.append(concept)

        for concept in self.concepts:
            visit(concept["name"])
            
        for concept in sorted_concepts:
            sample_data = self._generate_sample_data_for_concept(concept)
            if sample_data:
                sql_parts.append(sample_data)
        
        return '\n\n'.join(sql_parts)
    
    def _generate_sample_data_for_concept(self, concept: Dict[str, Any]) -> str:
        """
        Generate sample data for a single concept.
        
        Args:
            concept: Concept definition
            
        Returns:
            SQL INSERT statements
        """
        table_name = concept["name"]
        data_size = concept["data_size"]
        num_records_by_data_size = lambda ds: 100 if ds == "m" else 10
        num_records = num_records_by_data_size(data_size)
        
        # Generate sample records
        sample_records = []
        
        for i in range(1, num_records + 1):
            field_values = []
            field_names = []
            
            for field in concept["fields"]:
                field_name = field["name"]
                field_type = field["type"]
                
                # Skip calculated fields or SERIAL fields as they are handled by the DB
                if 'calculated' in field or field["_be_sql_type"] == "SERIAL":
                    continue
                
                # Skip state_info — let it default to NULL
                if field["name"] == "state_info":
                    continue

                # Generate sample value based on type
                if field_type == "string":
                    if field_name == "email":
                        value = f"'{table_name}_{field_name}_{i}@example.com'"
                    elif field_name == "state":
                        concept_workflow = self.schema_loader.business_schema.get("_concept_workflow", {}).get(table_name)
                        if concept_workflow:
                            states = concept_workflow["states"]
                            value = f"'{states[(i - 1) % len(states)]['name']}'"
                        else:
                            value = f"'{table_name}_{field_name}_{i}'"
                    else:
                        value = f"'{table_name}_{field_name}_{i}'"
                elif field_type == "integer":
                    value = str(i * 10)
                elif field_type == "decimal":
                    value = f"{i * 10}.{i:02d}"
                elif field_type == "boolean":
                    value = 'TRUE' if i % 2 == 0 else 'FALSE'
                elif field_type == "enum":
                    enum_values = field["enum_values"]
                    # Cycle through enum values
                    val_idx = (i - 1) % len(enum_values)
                    value = f"'{enum_values[val_idx]}'"
                elif field_type == "date":
                    # Cycle through days 1-28
                    day = ((i - 1) % 28) + 1
                    value = f"'2023-01-{day:02d}'"
                elif field_type == "datetime":
                    day = ((i - 1) % 28) + 1
                    value = f"'2023-01-{day:02d}T10:00:00Z'"
                elif field_type == "relation_to_one":
                    target_concept_name = field["target"]
                    if target_concept_name == concept["name"]:
                        # Recursive relationship (e.g., category.parent)
                        # Generic hierarchy: Level k has 2^(k+1) nodes.
                        # Each parent has 2 children.
                        if i <= 2:
                            value = "NULL"
                        else:
                            # Find level k such that i is in range [start_k, end_k]
                            # Level 0: 1-2
                            # Level 1: 3-6
                            # Level 2: 7-14
                            # ...
                            k = 1
                            while True:
                                level_start = 2 * (2**k - 1) + 1
                                level_end = 2 * (2**(k+1) - 1)
                                if level_start <= i <= level_end:
                                    prev_level_start = 2 * (2**(k-1) - 1) + 1
                                    parent_idx = (i - level_start) // 2 + prev_level_start
                                    value = str(parent_idx)
                                    break
                                k += 1
                                if k > 20: # Safety break
                                    value = "NULL"
                                    break
                    elif field.get("subtype") == "part_of":
                        # Triangular distribution: parent 1 gets 1, parent 2 gets 2, parent 3 gets 3...
                        # Find p such that sum(1..p-1) < i <= sum(1..p)
                        # sum(1..p) = p*(p+1)/2
                        p = 1
                        while (p * (p + 1)) // 2 < i:
                            p += 1
                        
                        # Check target count to avoid exceeding available parents
                        target_concept = self.concept_map.get(target_concept_name)
                        target_count = num_records_by_data_size(target_concept["data_size"]) if target_concept else 10
                        
                        parent_id = ((p - 1) % target_count) + 1
                        value = str(parent_id)
                    else:
                        # Check target concept data size to determine modulus
                        target_concept = self.concept_map.get(target_concept_name)
                        if target_concept:
                            target_size = target_concept["data_size"]
                            target_count = num_records_by_data_size(target_size)
                            # Distribute FKs across available target IDs (1 to target_count)
                            target_id = ((i - 1) % target_count) + 1
                            value = str(target_id)
                        else:
                             value = 'NULL'
                elif field_type == "relation_to_many":
                    continue
                else:
                    value = f"'{table_name}_{field_name}_{i}'"
                
                field_names.append(field_name)
                field_values.append(value)
            
            # Add timestamps
            field_names.extend(['_created_at', '_updated_at'])
            field_values.extend([f"'2023-01-01T10:00:00Z'", f"'2023-01-01T10:00:00Z'"])
            


            fields_str = ', '.join([f'"{field_name}"' for field_name in field_names])
            values_str = ', '.join(field_values)
            
            sample_records.append(f"({values_str})")
        
        if not sample_records:
            return ""
        
        return f'INSERT INTO "{table_name}" ({fields_str}) VALUES\n' + ",\n".join(sample_records) + ";"

    def _generate_presentation_triggers(self) -> List[str]:
        """
        Generate triggers for complex id_presentation fields.
        
        Returns:
            List of SQL statements for triggers
        """
        triggers = []
        
        for concept in self.concepts:
            presentation_config = concept["id_presentation"]
            if 'fields' not in presentation_config:
                continue
                
            presentation_fields = presentation_config["fields"]
            if not presentation_fields:
                continue
                
            # Check if complex
            is_complex = False
            for field_name in presentation_fields:
                if '.' in field_name:
                    is_complex = True
                    break
            
            if not is_complex:
                continue
                
            # Generate Trigger
            table_name = concept["name"]
            declarations = []
            selects = []
            parts = []
            
            for idx, field_name in enumerate(presentation_fields):
                part_var = f"part_{idx}"
                
                if '.' in field_name:
                    # Remote field: rel.field
                    rel_name, target_field = field_name.split('.', 1)
                    
                    # Find relationship
                    rel = None
                    
                    # Check fields for relation_to_one
                    for f in concept["fields"]:
                        if f["type"] == "relation_to_one" and f["name"] == rel_name:
                            rel = {
                                'type': 'belongs-to', 
                                'field_name': f["name"],
                                'target': f["target"]
                            }
                            break
                    

                    
                    if rel:
                        fk_col = rel.get("field_name", f"{rel["target"]}_id")
                        target_table = rel["target"]
                        declarations.append(f"{part_var} TEXT;")
                        
                        selects.append(f"""
    IF NEW."{fk_col}" IS NOT NULL THEN
        SELECT "{target_field}"::TEXT INTO {part_var} FROM "{target_table}" WHERE "id" = NEW."{fk_col}";
    END IF;"""
)
                        parts.append(f"COALESCE({part_var}, '')")
                    else:
                        parts.append("''")
                else:
                    # Local field
                    if field_name == "id":
                        parts.append(f"""COALESCE(NEW."id"::TEXT, '')""")
                    else:
                        field_exists = any(f["name"] == field_name for f in concept["fields"])
                        if field_exists:
                            parts.append(f"""COALESCE(NEW."{field_name}"::TEXT, '')""")
                        else:
                            parts.append("''")
            
            separator = presentation_config["separator"]
            # Escape single quotes in separator
            separator = separator.replace("'", "''")
            concat_expr = f" || '{separator}' || ".join(parts)

            
            trigger_sql = f"""

CREATE OR REPLACE FUNCTION "update_{table_name}_id_presentation"()
RETURNS TRIGGER AS $$
DECLARE
    {chr(10).join(declarations)}
BEGIN
    {chr(10).join(selects)}
    NEW."id_presentation" := {concat_expr};
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "{table_name}_update_id_presentation"
BEFORE INSERT OR UPDATE ON "{table_name}" 
FOR EACH ROW
EXECUTE FUNCTION "update_{table_name}_id_presentation"();
"""
            triggers.append(trigger_sql)
            
        return triggers
