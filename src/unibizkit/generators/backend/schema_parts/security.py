from typing import Any, Dict, List


def _generate_sso_hook(sso_config: Dict[str, Any]) -> str:
    role_claim = sso_config.get('role_claim', 'roles')
    default_role = sso_config.get('default_role', 'user')
    allowed_roles = ", ".join(f"'{role['name']}'" for role in sso_config["_all_roles"])
    return f"""
-- SSO access token hook: maps the SSO JWT roles claim to app_metadata.roles.
-- Email/password users keep their existing app_metadata.roles unchanged.
CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
AS $$
DECLARE
  claims jsonb;
  sso_roles jsonb;
  filtered_sso_roles jsonb;
BEGIN
  claims := event -> 'claims';

  SELECT coalesce(
    identity_data -> '{role_claim}',
    identity_data -> 'custom_claims' -> '{role_claim}',
    identity_data -> 'realm_access' -> 'roles'
  )
  INTO sso_roles
  FROM auth.identities
  WHERE user_id = (event ->> 'user_id')::uuid
    AND provider != 'email'
  LIMIT 1;

  IF sso_roles IS NOT NULL AND jsonb_typeof(sso_roles) = 'array' THEN
    SELECT coalesce(jsonb_agg(to_jsonb(role_name)), '[]'::jsonb)
    INTO filtered_sso_roles
    FROM (
      SELECT DISTINCT role_name
      FROM jsonb_array_elements_text(sso_roles) AS role_name
      WHERE role_name IN ({allowed_roles})
    ) valid_roles;
  ELSE
    filtered_sso_roles := NULL;
  END IF;

  IF filtered_sso_roles IS NOT NULL AND jsonb_array_length(filtered_sso_roles) > 0 THEN
    claims := jsonb_set(claims, '{{app_metadata}}',
      coalesce(claims -> 'app_metadata', '{{}}'::jsonb) ||
      jsonb_build_object('roles', filtered_sso_roles));
  ELSIF sso_roles IS NOT NULL THEN
    claims := jsonb_set(claims, '{{app_metadata}}',
      coalesce(claims -> 'app_metadata', '{{}}'::jsonb) ||
      jsonb_build_object('roles', to_jsonb(array['{default_role}'])));
  END IF;

  RETURN jsonb_set(event, '{{claims}}', claims);
END;
$$;

GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
"""


def _generate_auth_user_roles_trigger(security_config: Dict[str, Any]) -> str:
    default_role = security_config["registration"]["role"]
    allowed_roles = ", ".join(f"'{role['name']}'" for role in security_config["roles"])
    return f"""
-- Keep auth.users.raw_app_meta_data.roles aligned with SSO claims when present.
CREATE OR REPLACE FUNCTION public.sync_auth_user_roles()
RETURNS TRIGGER AS $$
DECLARE
  incoming_roles jsonb;
  filtered_roles jsonb;
BEGIN
  incoming_roles := coalesce(
    NEW.raw_user_meta_data -> 'roles',
    NEW.raw_user_meta_data -> 'custom_claims' -> 'roles',
    NEW.raw_user_meta_data -> 'realm_access' -> 'roles'
  );

  IF incoming_roles IS NOT NULL AND jsonb_typeof(incoming_roles) = 'array' THEN
    SELECT coalesce(jsonb_agg(to_jsonb(role_name)), '[]'::jsonb)
    INTO filtered_roles
    FROM (
      SELECT DISTINCT role_name
      FROM jsonb_array_elements_text(incoming_roles) AS role_name
      WHERE role_name IN ({allowed_roles})
    ) valid_roles;

    IF jsonb_array_length(filtered_roles) > 0 THEN
      NEW.raw_app_meta_data := coalesce(NEW.raw_app_meta_data, '{{}}'::jsonb) ||
        jsonb_build_object('roles', filtered_roles);
      RETURN NEW;
    END IF;
  END IF;

  IF TG_OP = 'INSERT' AND coalesce(NEW.raw_app_meta_data, '{{}}'::jsonb) -> 'roles' IS NULL THEN
    NEW.raw_app_meta_data := coalesce(NEW.raw_app_meta_data, '{{}}'::jsonb) ||
      jsonb_build_object('roles', to_jsonb(array['{default_role}']));
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_roles_sync ON auth.users;
CREATE TRIGGER on_auth_user_roles_sync
  BEFORE INSERT OR UPDATE OF raw_user_meta_data, raw_app_meta_data ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.sync_auth_user_roles();
"""


def _generate_security_owner_triggers(owner_tables: List[str]) -> str:
    trigger_sql = ["""
CREATE OR REPLACE FUNCTION "02_set_security_owner_id_trigger_function"()
RETURNS TRIGGER AS $$
BEGIN
    NEW."_security_owner_id" := auth.uid()::text;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""]

    for table in owner_tables:
        trigger_sql.append(f"""
DROP TRIGGER IF EXISTS "02_set_security_owner_id_trigger" ON "{table}";
CREATE TRIGGER "02_set_security_owner_id_trigger"
BEFORE INSERT ON "{table}"
FOR EACH ROW
EXECUTE FUNCTION "02_set_security_owner_id_trigger_function"();
""")

    return "\n".join(trigger_sql)


def generate_security_policies(
    concepts: List[Dict[str, Any]],
    concept_map: Dict[str, Any],
    security_config: Dict[str, Any],
    business_schema: Dict[str, Any],
) -> List[str]:
    policies = []

    sso_config = security_config["sso"]
    if sso_config["enabled"]:
        sso_config = {**sso_config, "_all_roles": security_config["roles"]}
        policies.append(_generate_sso_hook(sso_config))

    registration = security_config["registration"]
    if registration["allow"]:
        policies.append(_generate_auth_user_roles_trigger(security_config))

    _acl = security_config["_acl"]
    roles = security_config["roles"]
    all_role_names = set(r["name"] for r in roles)
    owner_tables = [
        concept["name"]
        for concept in concepts
        if any(f["name"] == "_security_owner_id" for f in concept["fields"])
    ]
    if owner_tables:
        policies.append(_generate_security_owner_triggers(owner_tables))

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

            for field in concept["fields"]:
                field_name = field["name"]
                if field_name.startswith("_"):
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

        # Include _anon if present in main rules (not in all_role_names)
        if "_anon" in main_rules:
            role_table_access["_anon"] = main_rules["_anon"]

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
            if role == "_anon":
                if access == "read":
                    policies.append(f"""
CREATE POLICY "anon_read_{table}" ON "{table}"
FOR SELECT
TO anon
USING (true);
""")
                continue

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
                owner_cond = f'{role_condition} AND "_security_owner_id" = auth.uid()::text'
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
        doc_roles = list(all_role_names)
        if "_anon" in main_acl or "_anon" in docs_field_acl:
            doc_roles.append("_anon")
        for role in doc_roles:
            access = docs_field_acl.get(role) or main_acl.get(role, "none")
            if access == "none":
                continue

            if role == "_anon":
                if access == "read":
                    policies.append(f"""
CREATE POLICY "anon_read_{doc_table}" ON "{doc_table}"
FOR SELECT
TO anon
USING (true);
""")
                continue

            role_condition = f"auth.jwt() -> 'app_metadata' -> 'roles' ? '{role}'"

            if access == "owner_write":
                owner_condition = (
                    f'EXISTS (SELECT 1 FROM "{owner_name}" '
                    f'WHERE "{owner_name}"."id" = "{doc_table}"."{fk_col}" '
                    f'AND "{owner_name}"."_security_owner_id" = auth.uid()::text)'
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
