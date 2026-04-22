from typing import Any, Dict, List


def generate_document_tables(concepts: List[Dict[str, Any]], security_config: Dict[str, Any], concept_workflows: Dict[str, Any] = None) -> List[str]:
    sql_parts = []

    for concept in concepts:
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

        sql_parts.append(f"""CREATE TRIGGER "{table_name}_updated_at_trigger"
  BEFORE UPDATE ON "{table_name}"
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();""")

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

        _acl = security_config.get("_acl", {})
        concept_acl = _acl.get(owner_name, {})
        docs_field_acl = concept_acl.get("_fields", {}).get("_documents", {})
        main_acl = concept_acl.get("_main", {})
        all_roles = security_config.get("roles", [])

        workflow = (concept_workflows or {}).get(owner_name)
        state_filter = ""
        if workflow:
            allowed_states = [s["name"] for s in workflow["states"]]
            # Will be narrowed per role below; compute full list as fallback
            state_filter = ", ".join(f"'{s}'" for s in allowed_states)

        owner_read_join = (
            f'EXISTS (SELECT 1 FROM "{table_name}" od '
            f'JOIN "{owner_name}" o ON o.id = od."{fk_col}" '
            f'WHERE od."storage_path" = objects.name '
            f'AND o."security_owner_id" = auth.uid()::text)'
        )
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

            for op in ("select", "insert", "update", "delete"):
                storage_sql.append(
                    f'DROP POLICY IF EXISTS "{role}_{op}_{bucket_name}" ON storage.objects;'
                )

            if access == "owner_write":
                # Build per-role state restriction for write operations
                role_write_join_read = owner_read_join
                role_write_join_insert = owner_insert_join
                if workflow:
                    role_allowed = [s["name"] for s in workflow["states"] if role in s["owners"]]
                    if role_allowed:
                        states_sql = ", ".join(f"'{s}'" for s in role_allowed)
                        role_write_join_read = (
                            f'EXISTS (SELECT 1 FROM "{table_name}" od '
                            f'JOIN "{owner_name}" o ON o.id = od."{fk_col}" '
                            f'WHERE od."storage_path" = objects.name '
                            f'AND o."security_owner_id" = auth.uid()::text '
                            f'AND o."state" IN ({states_sql}))'
                        )
                        role_write_join_insert = (
                            f'EXISTS (SELECT 1 FROM "{owner_name}" o '
                            f'WHERE o.id::text = (storage.foldername(objects.name))[1] '
                            f'AND o."security_owner_id" = auth.uid()::text '
                            f'AND o."state" IN ({states_sql}))'
                        )
                storage_sql.append(f"""CREATE POLICY "{role}_select_{bucket_name}" ON storage.objects
  FOR SELECT TO authenticated
  USING ({bucket_clause} AND {role_cond} AND {owner_read_join});""")
                storage_sql.append(f"""CREATE POLICY "{role}_insert_{bucket_name}" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK ({bucket_clause} AND {role_cond} AND {role_write_join_insert});""")
                storage_sql.append(f"""CREATE POLICY "{role}_update_{bucket_name}" ON storage.objects
  FOR UPDATE TO authenticated
  USING ({bucket_clause} AND {role_cond} AND {role_write_join_insert})
  WITH CHECK ({bucket_clause} AND {role_cond} AND {role_write_join_insert});""")
                storage_sql.append(f"""CREATE POLICY "{role}_delete_{bucket_name}" ON storage.objects
  FOR DELETE TO authenticated
  USING ({bucket_clause} AND {role_cond} AND {role_write_join_read});""")
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

        for old_op in ("read", "write", "update", "delete"):
            storage_sql.append(
                f'DROP POLICY IF EXISTS "authenticated_{old_op}_{bucket_name}" ON storage.objects;'
            )

        sql_parts.append("\n".join(storage_sql))

    return sql_parts
