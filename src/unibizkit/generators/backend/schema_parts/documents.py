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
        cols.append('  "_created_at" TIMESTAMP WITH TIME ZONE,')
        cols.append('  "_updated_at" TIMESTAMP WITH TIME ZONE,')
        cols.append(f'  CONSTRAINT "{table_name}_tag_check" CHECK ("tag" IN ({tags_sql})),')
        if versioned:
            cols.append(f'  UNIQUE ("{fk_col}", "tag", "version")')
        else:
            cols.append(f'  UNIQUE ("{fk_col}", "tag")')

        create_sql = f'CREATE TABLE "{table_name}" (\n' + '\n'.join(cols) + '\n);'
        sql_parts.append(create_sql)

        if versioned:
            sql_parts.append(f"""CREATE OR REPLACE FUNCTION "{table_name}_manage_current_func"()
RETURNS TRIGGER AS $$
DECLARE
  v_next_id INTEGER;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD."is_current" = TRUE THEN
      SELECT "id" INTO v_next_id
      FROM "{table_name}"
      WHERE "{fk_col}" = OLD."{fk_col}"
        AND "tag" = OLD."tag"
        AND "id" != OLD."id"
      ORDER BY "version" DESC
      LIMIT 1;
      IF v_next_id IS NOT NULL THEN
        UPDATE "{table_name}" SET "is_current" = TRUE WHERE "id" = v_next_id;
      END IF;
    END IF;
    RETURN OLD;
  END IF;
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
  AFTER INSERT OR UPDATE OF "is_current" OR DELETE ON "{table_name}"
  FOR EACH ROW EXECUTE FUNCTION "{table_name}_manage_current_func"();""")

        _acl = security_config.get("_acl", {})
        concept_acl = _acl.get(owner_name, {})
        docs_field_acl = concept_acl.get("_fields", {}).get("_documents", {})
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
            f'AND o."_security_owner_id" = auth.uid()::text)'
        )
        owner_insert_join = (
            f'EXISTS (SELECT 1 FROM "{owner_name}" o '
            f'WHERE o.id::text = (storage.foldername(objects.name))[1] '
            f'AND o."_security_owner_id" = auth.uid()::text)'
        )

        bucket_clause = f"bucket_id = '{bucket_name}'"

        # A concept readable by anonymous visitors (e.g. a storefront catalog) needs its
        # documents served publicly so <img> tags resolve without a session. Gate the
        # public flag on _anon read access; private concepts (orders, invoices) stay closed.
        anon_doc_access = docs_field_acl.get("_anon", "none")
        is_public = anon_doc_access == "read"
        public_sql = "true" if is_public else "false"

        storage_sql = [f"""-- Storage bucket for {owner_name} documents
INSERT INTO storage.buckets (id, name, public)
VALUES ('{bucket_name}', '{bucket_name}', {public_sql})
ON CONFLICT (id) DO UPDATE SET public = EXCLUDED.public;"""]

        if is_public:
            storage_sql.append(
                f'DROP POLICY IF EXISTS "anon_select_{bucket_name}" ON storage.objects;'
            )
            storage_sql.append(f"""CREATE POLICY "anon_select_{bucket_name}" ON storage.objects
  FOR SELECT TO anon
  USING ({bucket_clause});""")

        for r in all_roles:
            role = r["name"]
            access = docs_field_acl.get(role, "none")
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
                            f'AND o."_security_owner_id" = auth.uid()::text '
                            f'AND o."state" IN ({states_sql}))'
                        )
                        role_write_join_insert = (
                            f'EXISTS (SELECT 1 FROM "{owner_name}" o '
                            f'WHERE o.id::text = (storage.foldername(objects.name))[1] '
                            f'AND o."_security_owner_id" = auth.uid()::text '
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

    if any(c["documents"]["enabled"] for c in concepts):
        sql_parts.append("""CREATE OR REPLACE FUNCTION public.sync_document_on_upload()
RETURNS TRIGGER AS $$
DECLARE
  v_concept TEXT;
  v_parts   TEXT[];
  v_rec_id  INTEGER;
  v_tag     TEXT;
  v_version INTEGER;
  v_tbl     TEXT;
  v_fk      TEXT;
BEGIN
  IF NEW.bucket_id NOT LIKE '%-documents' THEN
    RETURN NEW;
  END IF;
  v_concept := replace(NEW.bucket_id, '-documents', '');
  v_tbl     := v_concept || '_document';
  v_fk      := v_concept || '_id';
  v_parts   := string_to_array(NEW.name, '/');
  v_rec_id  := v_parts[1]::INTEGER;
  v_tag     := v_parts[2];
  IF array_length(v_parts, 1) >= 4 AND v_parts[3] ~ '^v[0-9]+$' THEN
    v_version := substring(v_parts[3] FROM 2)::INTEGER;
    EXECUTE format(
      'INSERT INTO public.%I (%I, tag, version, is_current, storage_path) VALUES ($1, $2, $3, true, $4)',
      v_tbl, v_fk
    ) USING v_rec_id, v_tag, v_version, NEW.name;
  ELSE
    EXECUTE format(
      'INSERT INTO public.%I (%I, tag, storage_path) VALUES ($1, $2, $3)
       ON CONFLICT (%I, tag) DO UPDATE SET storage_path = EXCLUDED.storage_path',
      v_tbl, v_fk, v_fk
    ) USING v_rec_id, v_tag, NEW.name;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS sync_document_on_upload ON storage.objects;
CREATE TRIGGER sync_document_on_upload
  AFTER INSERT ON storage.objects
  FOR EACH ROW EXECUTE FUNCTION public.sync_document_on_upload();

CREATE OR REPLACE FUNCTION public.cleanup_document_on_delete()
RETURNS TRIGGER AS $$
DECLARE
  v_concept TEXT;
  v_tbl     TEXT;
BEGIN
  IF OLD.bucket_id NOT LIKE '%-documents' THEN
    RETURN OLD;
  END IF;
  v_concept := replace(OLD.bucket_id, '-documents', '');
  v_tbl     := v_concept || '_document';
  EXECUTE format(
    'DELETE FROM public.%I WHERE storage_path = $1',
    v_tbl
  ) USING OLD.name;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS cleanup_document_on_delete ON storage.objects;
CREATE TRIGGER cleanup_document_on_delete
  AFTER DELETE ON storage.objects
  FOR EACH ROW EXECUTE FUNCTION public.cleanup_document_on_delete();""")

    return sql_parts
