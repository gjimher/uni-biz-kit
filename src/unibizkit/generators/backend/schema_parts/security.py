from typing import Any, Dict, List


def generate_security_policies(
    concepts: List[Dict[str, Any]],
    concept_map: Dict[str, Any],
    security_config: Dict[str, Any],
    business_schema: Dict[str, Any],
) -> List[str]:
    policies = []

    registration = security_config["registration"]
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

    _acl = security_config["_acl"]
    roles = security_config["roles"]
    all_role_names = set(r["name"] for r in roles)

    join_tables = []
    for concept in concepts:
        for field in concept["fields"]:
            if field["type"] == "relation_to_many":
                target_name = field["target"]
                target_concept = concept_map.get(target_name)
                if not target_concept:
                    continue
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

    all_tables = [c["name"] for c in concepts] + join_tables
    concept_workflows = business_schema["_concept_workflow"]

    # Map: child concept name -> list of {fk_field, parent, workflow}
    child_parent_workflows: Dict[str, list] = {}
    for concept in concepts:
        for field in concept["fields"]:
            if field["type"] == "relation_to_one":
                parent_name = field["target"]
                workflow = concept_workflows.get(parent_name)
                if workflow:
                    child_parent_workflows.setdefault(concept["name"], []).append({
                        "fk_field": field["name"],
                        "parent": parent_name,
                        "workflow": workflow,
                    })

    def build_parent_state_condition(table: str, role: str) -> str:
        """Returns SQL AND-clause to restrict writes to parent workflow states the role owns."""
        parts = []
        for entry in child_parent_workflows.get(table, []):
            allowed_states = [s["name"] for s in entry["workflow"]["states"] if role in s["owners"]]
            if allowed_states:
                states_sql = ", ".join(f"'{s}'" for s in allowed_states)
                parts.append(
                    f'EXISTS (SELECT 1 FROM "{entry["parent"]}" p'
                    f' WHERE p."id" = "{entry["fk_field"]}" AND p."state" IN ({states_sql}))'
                )
        return (" AND " + " AND ".join(parts)) if parts else ""

    for table in all_tables:
        policies.append(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')

        concept_acl = _acl.get(table)
        workflow = concept_workflows.get(table)

        if not concept_acl:
            policies.append(f"""
CREATE POLICY "allow_all_authenticated_{table}" ON "{table}"
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);
""")
            continue

        concept = concept_map.get(table)
        main_rules = concept_acl["_main"]
        if concept:
            trigger_checks = []

            if workflow:
                for state in workflow["states"]:
                    state_name = state["name"]
                    owners = state["owners"]
                    roles_json_array = ", ".join(f"'{r}'" for r in owners)
                    trigger_checks.append(f"""
    IF (TG_OP IN ('UPDATE', 'DELETE') AND OLD."state" = '{state_name}') THEN
        IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Insufficient privilege for state {state_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;""")
                    trigger_checks.append(f"""
    IF (TG_OP = 'INSERT' AND NEW."state" = '{state_name}') THEN
        IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Insufficient privilege for state {state_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;""")

            trigger_checks.append("""
    -- System timestamps are immutable / system-controlled
    IF (TG_OP = 'INSERT') THEN
        NEW."_created_at" := CURRENT_TIMESTAMP;
        NEW."_updated_at" := CURRENT_TIMESTAMP;
    ELSIF (TG_OP = 'UPDATE' AND NEW."_created_at" IS DISTINCT FROM OLD."_created_at") THEN
        RAISE EXCEPTION 'Permission denied: _created_at is immutable' USING ERRCODE = 'insufficient_privilege';
    END IF;""")

            has_security_owner_id = any(f["name"] == "security_owner_id" for f in concept["fields"])
            if has_security_owner_id:
                trigger_checks.append("""
    -- security_owner_id must be auth.uid() on insert, and is immutable after that
    IF (TG_OP = 'INSERT' AND NEW."security_owner_id" IS DISTINCT FROM auth.uid()::text) THEN
        RAISE EXCEPTION 'Permission denied: security_owner_id must be auth.uid()' USING ERRCODE = 'insufficient_privilege';
    ELSIF (TG_OP = 'UPDATE' AND NEW."security_owner_id" IS DISTINCT FROM OLD."security_owner_id") THEN
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

        role_table_access = {}
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
                parent_state_cond = build_parent_state_condition(table, role)
                owner_cond = f'{role_condition} AND "security_owner_id" = auth.uid()::text'
                policies.append(f"""
CREATE POLICY "{role}_owner_select_{table}" ON "{table}"
FOR SELECT
TO authenticated
USING ({owner_cond});
""")
                policies.append(f"""
CREATE POLICY "{role}_owner_insert_{table}" ON "{table}"
FOR INSERT
TO authenticated
WITH CHECK ({owner_cond}{parent_state_cond});
""")
                policies.append(f"""
CREATE POLICY "{role}_owner_update_{table}" ON "{table}"
FOR UPDATE
TO authenticated
USING ({owner_cond})
WITH CHECK ({owner_cond}{parent_state_cond});
""")
                policies.append(f"""
CREATE POLICY "{role}_owner_delete_{table}" ON "{table}"
FOR DELETE
TO authenticated
USING ({owner_cond}{parent_state_cond});
""")

    # RLS for document tables
    for concept in concepts:
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
                # Add workflow state check for write operations
                doc_workflow = concept_workflows.get(owner_name)
                state_extra = ""
                if doc_workflow:
                    allowed_states = [s["name"] for s in doc_workflow["states"] if role in s["owners"]]
                    if allowed_states:
                        states_sql = ", ".join(f"'{s}'" for s in allowed_states)
                        state_extra = (
                            f' AND EXISTS (SELECT 1 FROM "{owner_name}" p'
                            f' WHERE p."id" = "{doc_table}"."{fk_col}" AND p."state" IN ({states_sql}))'
                        )
                select_cond = f"{role_condition} AND {owner_condition}"
                write_cond = f"{role_condition} AND {owner_condition}{state_extra}"
                policies.append(f"""
CREATE POLICY "{role}_select_{doc_table}" ON "{doc_table}"
FOR SELECT
TO authenticated
USING ({select_cond});
""")
                policies.append(f"""
CREATE POLICY "{role}_insert_{doc_table}" ON "{doc_table}"
FOR INSERT
TO authenticated
WITH CHECK ({write_cond});
""")
                policies.append(f"""
CREATE POLICY "{role}_update_{doc_table}" ON "{doc_table}"
FOR UPDATE
TO authenticated
USING ({select_cond})
WITH CHECK ({write_cond});
""")
                policies.append(f"""
CREATE POLICY "{role}_delete_{doc_table}" ON "{doc_table}"
FOR DELETE
TO authenticated
USING ({write_cond});
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
