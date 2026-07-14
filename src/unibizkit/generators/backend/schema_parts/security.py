from typing import Any, Dict, List


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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


def _profile_insert_columns(concept: Dict[str, Any]) -> List[str]:
    # Any other column is covered by its SQL DEFAULT, a from_metadata default
    # (see _profile_metadata_column_values), or stays NULL — the SchemaProcessor
    # rejects profile concepts with required fields that have no default.
    columns = ["_user", "_user_email"]
    if any(f["name"] == "_security_owner_id" for f in concept["fields"]):
        columns.append("_security_owner_id")
    return columns


def _profile_metadata_column_values(concept: Dict[str, Any]) -> List[tuple]:
    """Columns of a fresh profile filled from the token's user_metadata.

    Covers fields whose default is from_metadata(key[, key...]): the first
    non-empty key wins, so one field can accept both the signUp options.data key
    and the SSO claim (e.g. 'from_metadata(first_name, given_name)'). When every
    key is empty the column is left NULL. The metadata comes from the token
    claims (target_metadata parameter) — sync_role_profiles must not read
    auth.users.
    """
    values = []
    for field in concept["fields"]:
        default = field.get("default")
        if not (isinstance(default, str) and default.startswith("from_metadata(")):
            continue
        keys = [k.strip() for k in default[len("from_metadata("):].rstrip(")").split(",")]
        parts = []
        for key in keys:
            key_sql = _sql_literal(key)
            parts.append(f"nullif(target_metadata->>{key_sql}, '')")
            # GoTrue nests non-standard OIDC claims (e.g. Keycloak's given_name)
            # under custom_claims, same as the roles lookup in sync_auth_user_roles.
            parts.append(f"nullif(target_metadata->'custom_claims'->>{key_sql}, '')")
        expr = f"coalesce({', '.join(parts)})"
        values.append((field["name"], expr))
    return values


def _owner_backfill_sql(profile_concept: str, concept_map: Dict[str, Any]) -> str:
    """UPDATEs run when a profile is linked to an auth user for the first time.

    Rows that are part_of the profile (composition implies ownership) may exist
    before the user ever logs in — seeded demo data or records prepared by an
    admin. They carry a NULL _security_owner_id (the owner trigger only fires
    for authenticated inserts), so owner_write RLS would hide them from the very
    user they belong to. Transfer those orphans to the claiming user.
    """
    updates = []
    for concept in concept_map.values():
        if not any(f["name"] == "_security_owner_id" for f in concept["fields"]):
            continue
        for field in concept["fields"]:
            if (
                field["type"] == "relation_to_one"
                and field.get("subtype") == "part_of"
                and field["target"] == profile_concept
            ):
                updates.append(f"""
      UPDATE {_quote_ident(concept["name"])} AS linked
      SET "_security_owner_id" = target_user_id::text
      FROM {_quote_ident(profile_concept)} AS profile
      WHERE profile."_user" = target_user_id
        AND linked.{_quote_ident(field["name"])} = profile."id"
        AND linked."_security_owner_id" IS NULL;""")
    return "".join(updates)


def _generate_profile_sync_function(
    concept_map: Dict[str, Any],
    security_config: Dict[str, Any],
) -> str:
    sync_parts = []
    for mapping in security_config["_profile_concepts"]:
        role_name = mapping["role"]
        concept_name = mapping["concept"]
        concept = concept_map[concept_name]
        table_sql = _quote_ident(concept_name)
        role_sql = _sql_literal(role_name)
        has_security_owner_id = any(f["name"] == "_security_owner_id" for f in concept["fields"])
        insert_columns = _profile_insert_columns(concept)
        metadata_values = _profile_metadata_column_values(concept)
        insert_columns_sql = ", ".join(
            _quote_ident(column)
            for column in insert_columns + [name for name, _ in metadata_values]
        )

        def _col_value(column: str) -> str:
            if column == "_user":
                return "target_user_id"
            if column == "_user_email":
                return "target_email"
            if column == "_security_owner_id":
                return "target_user_id::text"
            return "NULL"

        insert_values_sql = ", ".join(
            [_col_value(col) for col in insert_columns]
            + [expr for _, expr in metadata_values]
        )
        owner_id_set = ',\n          "_security_owner_id" = target_user_id::text' if has_security_owner_id else ""
        owner_backfill = _owner_backfill_sql(concept_name, concept_map)

        sync_parts.append(f"""
  -- Sync {role_name} profiles in {concept_name}.
  IF target_roles ? {role_sql} THEN
    IF NOT EXISTS (SELECT 1 FROM {table_sql} WHERE "_user" = target_user_id) THEN
      -- A same-email login with a different UUID supersedes the previously linked profile.
      UPDATE {table_sql} AS profile
      SET "_user_prev"       = profile."_user",
          "_user_email_prev" = profile."_user_email",
          "_user"            = NULL,
          "_user_email"      = NULL
      WHERE profile."_user_email" = target_email
        AND profile."_user" IS NOT NULL
        AND profile."_user" <> target_user_id;

      -- Reactivate a previously deactivated profile for this exact UUID.
      UPDATE {table_sql}
      SET "_user"           = target_user_id,
          "_user_email"     = target_email,
          "_user_prev"      = NULL,
          "_user_email_prev" = NULL{owner_id_set}
      WHERE "_user_prev" = target_user_id
        AND "_user" IS NULL;

      -- Claim a pre-seeded profile matched by email (first-time link, no prior UUID).
      IF NOT EXISTS (SELECT 1 FROM {table_sql} WHERE "_user" = target_user_id) THEN
        UPDATE {table_sql}
        SET "_user"              = target_user_id,
            "_user_email"        = target_email,
            "_user_pending_link" = NULL{owner_id_set}
        WHERE "id" = (
          SELECT "id" FROM {table_sql}
          WHERE "_user_pending_link" = target_email AND "_user" IS NULL
          ORDER BY "id"
          LIMIT 1
        );
      END IF;

      -- Create a fresh profile if still unlinked. Registration metadata from the
      -- token claims (signUp options.data) fills the matching profile columns.
      INSERT INTO {table_sql} ({insert_columns_sql})
      SELECT {insert_values_sql}
      WHERE NOT EXISTS (SELECT 1 FROM {table_sql} WHERE "_user" = target_user_id);

      -- First link for this user: adopt pre-existing rows that are part_of the
      -- claimed profile (seeded or admin-prepared) and still have no owner.{owner_backfill}
    END IF;
  ELSE
    -- User no longer holds the role: deactivate their profile.
    UPDATE {table_sql}
    SET "_user_prev"       = "_user",
        "_user_email_prev" = "_user_email",
        "_user"            = NULL,
        "_user_email"      = NULL
    WHERE "_user" = target_user_id;
  END IF;""")

    sync_sql = "\n".join(sync_parts)
    return f"""
-- Keep role profile concepts linked to the current auth state.
-- target_metadata is the token's user_metadata (registration signUp options.data);
-- the function works from token identity only, with no user-table lookups.
DROP FUNCTION IF EXISTS public.sync_role_profiles(uuid, text, jsonb);
CREATE OR REPLACE FUNCTION public.sync_role_profiles(target_user_id uuid, target_email text, target_roles jsonb, target_metadata jsonb DEFAULT '{{}}'::jsonb)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
BEGIN
  IF target_user_id IS NULL OR target_email IS NULL THEN
    RETURN;
  END IF;

  target_roles := coalesce(target_roles, '[]'::jsonb);
  target_metadata := coalesce(target_metadata, '{{}}'::jsonb);
  PERFORM set_config('request.jwt.claims', '', true);
{sync_sql}
END;
$$;

GRANT EXECUTE ON FUNCTION public.sync_role_profiles(uuid, text, jsonb, jsonb) TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.sync_role_profiles(uuid, text, jsonb, jsonb) FROM authenticated, anon, public;
"""


def _generate_access_token_hook(security_config: Dict[str, Any], workflow_config: Dict[str, Any]) -> str:
    sso_config = security_config["sso"]
    role_claim = sso_config.get('role_claim', 'roles')
    default_role = sso_config.get('default_role', 'user')
    sso_enabled = "TRUE" if sso_config["enabled"] else "FALSE"
    allowed_roles = ", ".join(f"'{role['name']}'" for role in security_config["roles"])
    sync_profiles_sql = ""
    if security_config["_profile_concepts"]:
        sync_profiles_sql = """
  PERFORM public.sync_role_profiles(current_user_id, current_email, effective_roles,
    coalesce(claims -> 'user_metadata', '{}'::jsonb));
"""

    user_directory_sql = ""
    if workflow_config["_concept_workflow"]:
        user_directory_sql = """
  -- Refresh the _user_directory discovery cache (workflow task assignment).
  IF current_email IS NOT NULL THEN
    INSERT INTO public._user_directory ("email", "_user", "roles", "source", "last_seen_at")
    VALUES (lower(current_email), current_user_id, effective_roles, 'login', now())
    ON CONFLICT ("email") DO UPDATE
    SET "_user" = EXCLUDED."_user",
        "roles" = EXCLUDED."roles",
        "source" = 'login',
        "last_seen_at" = now();
  END IF;
"""

    return f"""
-- Access token hook: resolves final roles and synchronizes role profile concepts.
CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
AS $$
DECLARE
  claims jsonb;
  sso_roles jsonb;
  filtered_sso_roles jsonb;
  effective_roles jsonb;
  current_user_id uuid;
  current_email text;
BEGIN
  current_user_id := (event ->> 'user_id')::uuid;
  claims := event -> 'claims';
  effective_roles := coalesce(claims -> 'app_metadata' -> 'roles', '[]'::jsonb);

  IF {sso_enabled} THEN
    sso_roles := coalesce(
      claims -> '{role_claim}',
      claims -> 'user_metadata' -> '{role_claim}',
      claims -> 'custom_claims' -> '{role_claim}',
      claims -> 'realm_access' -> 'roles'
    );

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
      effective_roles := filtered_sso_roles;
      claims := jsonb_set(claims, '{{app_metadata}}',
        coalesce(claims -> 'app_metadata', '{{}}'::jsonb) ||
        jsonb_build_object('roles', filtered_sso_roles));
    ELSIF sso_roles IS NOT NULL THEN
      effective_roles := to_jsonb(array['{default_role}']);
      claims := jsonb_set(claims, '{{app_metadata}}',
        coalesce(claims -> 'app_metadata', '{{}}'::jsonb) ||
        jsonb_build_object('roles', effective_roles));
    END IF;
  END IF;

  current_email := claims ->> 'email';
{user_directory_sql}{sync_profiles_sql}
  RETURN jsonb_set(event, '{{claims}}', claims);
END;
$$;

GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
"""


def _generate_security_owner_triggers(owner_tables: List[str]) -> str:
    trigger_sql = ["""
CREATE OR REPLACE FUNCTION "02_set_security_owner_id_trigger_function"()
RETURNS TRIGGER AS $$
BEGIN
    IF auth.uid() IS NOT NULL THEN
        NEW."_security_owner_id" := auth.uid()::text;
    END IF;
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
    workflow_config: Dict[str, Any],
) -> List[str]:
    policies = []

    if security_config["_profile_concepts"]:
        policies.append(_generate_profile_sync_function(concept_map, security_config))

    policies.append(_generate_access_token_hook(security_config, workflow_config))

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
    concept_workflows = workflow_config["_concept_workflow"]

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

            for field in concept["fields"]:
                if field["required"] != "ask_after_login":
                    continue
                field_name = field["name"]
                trigger_checks.append(f"""
    -- '{field_name}' is required "ask_after_login": once filled it cannot be cleared.
    IF TG_OP = 'UPDATE' AND OLD."{field_name}" IS NOT NULL AND NEW."{field_name}" IS NULL THEN
        RAISE EXCEPTION 'Field {field_name} is required and cannot be cleared' USING ERRCODE = 'check_violation';
    END IF;""")

            if workflow:
                trigger_checks.append("""
    IF TG_OP = 'UPDATE'
       AND (
           NEW."state" IS DISTINCT FROM OLD."state"
           OR NEW."state_info" IS DISTINCT FROM OLD."state_info"
       )
    THEN
        RAISE EXCEPTION 'Workflow state can only be changed by workflow-transition' USING ERRCODE = 'insufficient_privilege';
    END IF;""")
                for state in workflow["states"]:
                    state_name = state["name"]
                    owners = state["owners"]
                    roles_json_array = ", ".join(f"'{r}'" for r in owners)
                    # Owners guard business edits; a change limited to
                    # state_task_owner is governed by the assigners check below,
                    # so it is carved out of the owners comparison.
                    trigger_checks.append(f"""
    IF (TG_OP = 'DELETE' AND OLD."state" = '{state_name}')
       OR (
           TG_OP = 'UPDATE' AND OLD."state" = '{state_name}'
           -- _updated_at is already bumped by the 01_set_system_timestamps trigger
           AND (to_jsonb(NEW) - 'state_task_owner' - '_updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'state_task_owner' - '_updated_at')
       )
    THEN
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

                    assigners = state["assigners"]
                    if assigners:
                        assigners_json_array = ", ".join(f"'{r}'" for r in assigners)
                        assigners_guard = f"""
        IF NOT (user_roles ?| array[{assigners_json_array}]) THEN
            RAISE EXCEPTION 'Insufficient privilege to assign task in state {state_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;"""
                    else:
                        assigners_guard = f"""
        RAISE EXCEPTION 'Task assignment is not allowed in state {state_name}' USING ERRCODE = 'insufficient_privilege';"""
                    trigger_checks.append(f"""
    IF (TG_OP = 'UPDATE' AND OLD."state" = '{state_name}' AND NEW."state_task_owner" IS DISTINCT FROM OLD."state_task_owner")
       OR (TG_OP = 'INSERT' AND NEW."state" = '{state_name}' AND NEW."state_task_owner" IS NOT NULL)
    THEN{assigners_guard}
    END IF;""")

            for field in concept["fields"]:
                field_name = field["name"]
                if field_name.startswith("_"):
                    continue
                if field.get("type") == "relation_to_many":
                    continue
                field_rules = concept_acl["_fields"].get(field_name, {})

                allowed_roles = []
                for role in all_role_names:
                    access = field_rules.get(role, "none")
                    if access in ("write", "owner_write"):
                        allowed_roles.append(role)

                if set(allowed_roles) != all_role_names:
                    if allowed_roles:
                        roles_json_array = ", ".join(f"'{r}'" for r in allowed_roles)
                        role_guard = f"""IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Permission denied for field {field_name}' USING ERRCODE = 'insufficient_privilege';
        END IF;"""
                    else:
                        role_guard = f"RAISE EXCEPTION 'Permission denied for field {field_name}' USING ERRCODE = 'insufficient_privilege';"
                    check = f"""
    -- Check field '{field_name}'
    IF (TG_OP = 'UPDATE' AND NEW."{field_name}" IS DISTINCT FROM OLD."{field_name}") OR (TG_OP = 'INSERT' AND NEW."{field_name}" IS NOT NULL) THEN
        {role_guard}
    END IF;"""
                    trigger_checks.append(check)

            if trigger_checks:
                trigger_name = f"{table}_security"
                trigger_func = f"""
CREATE OR REPLACE FUNCTION "{trigger_name}_func"()
RETURNS TRIGGER AS $$
DECLARE
    claims jsonb := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    user_roles jsonb := coalesce(auth.jwt() -> 'app_metadata' -> 'roles', '[]'::jsonb);
BEGIN
    -- Bypass trigger for system operations (like seeding data directly)
    -- Bypass for service_role (edge functions writing by_rules fields)
    IF claims IS NULL OR claims ->> 'role' = 'service_role' THEN
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

        # A writable field under read concept access intentionally grants only
        # SELECT + UPDATE. Field triggers still restrict which columns may change.
        for field_rules in concept_acl["_fields"].values():
            for role, field_access in field_rules.items():
                if field_access == "write" and role_table_access.get(role) == "read":
                    role_table_access[role] = "field_write"

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
            elif access == "field_write":
                policies.append(f"""
CREATE POLICY "{role}_select_{table}" ON "{table}"
FOR SELECT
TO authenticated
USING ({role_condition});
""")
                policies.append(f"""
CREATE POLICY "{role}_update_{table}" ON "{table}"
FOR UPDATE
TO authenticated
USING ({role_condition})
WITH CHECK ({role_condition});
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
            access = docs_field_acl.get(role, "none")
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
