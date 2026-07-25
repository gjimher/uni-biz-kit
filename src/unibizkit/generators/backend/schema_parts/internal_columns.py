import re
from typing import Any, Dict, List, Optional


API_ROLES = "anon, authenticated, service_role"
PROTECT_INTERNAL_COLUMNS_TRIGGER = "00_protect_internal_columns_trigger"
PROTECT_INTERNAL_COLUMNS_FUNCTION = "00_protect_internal_columns_trigger_function"
SET_SYSTEM_TIMESTAMPS_TRIGGER = "01_set_system_timestamps_trigger"
SET_SYSTEM_TIMESTAMPS_FUNCTION = "01_set_system_timestamps_trigger_function"


def _table_name(table: Any) -> str:
    if isinstance(table, dict):
        return table["name"]
    return table


def generate_internal_column_protection(
    tables: List[Any],
    trigger_protected_cols: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """Generate the 00_protect trigger for every table.

    The trigger rejects writes to:
    - changes to the conventional ``id`` primary key
    - any column whose name starts with '_' (internal system columns)
    - any extra column listed in *trigger_protected_cols* for that table
      (rollup, copy, copy_logged_on_insert calculated fields)

    Extra column names are passed as trigger arguments so the single shared
    function can serve all tables without per-table variants.

    The check is skipped when there is no JWT context (direct DB access) or
    when called from within a trigger chain (pg_trigger_depth() > 1), which
    allows system triggers to write these columns freely.
    """
    if trigger_protected_cols is None:
        trigger_protected_cols = {}

    sql_parts = [f"""
CREATE OR REPLACE FUNCTION "{PROTECT_INTERNAL_COLUMNS_FUNCTION}"()
RETURNS TRIGGER AS $$
DECLARE
    new_row JSONB;
    old_row JSONB;
    claims JSONB;
    column_name TEXT;
    i INT;
BEGIN
    -- Skip when called from direct DB access (no JWT) or from a trigger chain.
    IF current_setting('request.jwt.claims', true) IS NULL
       OR current_setting('request.jwt.claims', true) = ''
       OR pg_trigger_depth() > 1
    THEN
        RETURN NEW;
    END IF;

    claims := current_setting('request.jwt.claims', true)::jsonb;
    new_row := to_jsonb(NEW);

    -- A row id is immutable through every JWT-backed API role, including
    -- service_role. Trusted direct database sessions have already returned
    -- above and may still re-key rows for administrative repair work.
    IF TG_OP = 'UPDATE' THEN
        old_row := to_jsonb(OLD);
        IF (new_row -> 'id') IS DISTINCT FROM (old_row -> 'id') THEN
            RAISE EXCEPTION
                'Permission denied: id is immutable through the API (table: %)',
                TG_TABLE_NAME
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    -- Edge functions write by_rules fields using service_role, but they may
    -- not change ids (the check above deliberately runs first).
    IF claims ->> 'role' = 'service_role' THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'INSERT' THEN
        -- Reject non-null writes to _-prefixed columns.
        -- NOTE: calculated columns (rollup/copy) are NOT checked on INSERT because
        -- PostgreSQL applies DEFAULT values before BEFORE triggers fire, making it
        -- impossible to distinguish user-supplied values from defaults. Those fields
        -- are always overridden by their own BEFORE INSERT triggers anyway.
        FOR column_name IN
            SELECT key
            FROM jsonb_object_keys(new_row) AS key
            WHERE key LIKE '\\_%' ESCAPE '\\'
        LOOP
            IF new_row -> column_name <> 'null'::jsonb THEN
                RAISE EXCEPTION
                    'Permission denied: % must be null on insert (table: %)',
                    column_name, TG_TABLE_NAME
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
        END LOOP;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Reject changes to _-prefixed columns.
        FOR column_name IN
            SELECT key
            FROM jsonb_object_keys(new_row) AS key
            WHERE key LIKE '\\_%' ESCAPE '\\'
        LOOP
            IF (new_row -> column_name) IS DISTINCT FROM (old_row -> column_name) THEN
                RAISE EXCEPTION
                    'Permission denied: % is trigger-controlled (table: %)',
                    column_name, TG_TABLE_NAME
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
        END LOOP;
        -- Reject changes to trigger-controlled calculated columns.
        FOR i IN 0..TG_NARGS - 1 LOOP
            column_name := TG_ARGV[i];
            IF (new_row -> column_name) IS DISTINCT FROM (old_row -> column_name) THEN
                RAISE EXCEPTION
                    'Permission denied: % is trigger-controlled (table: %)',
                    column_name, TG_TABLE_NAME
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""]

    for table in tables:
        name = _table_name(table)
        extra_cols = trigger_protected_cols.get(name, [])
        col_args = ", ".join(f"'{c}'" for c in extra_cols)
        sql_parts.append(f"""
DROP TRIGGER IF EXISTS "{PROTECT_INTERNAL_COLUMNS_TRIGGER}" ON "{name}";
CREATE TRIGGER "{PROTECT_INTERNAL_COLUMNS_TRIGGER}"
BEFORE INSERT OR UPDATE ON "{name}"
FOR EACH ROW
EXECUTE FUNCTION "{PROTECT_INTERNAL_COLUMNS_FUNCTION}"({col_args});
""")

    return sql_parts


def _created_table_columns(schema_sql: str) -> Dict[str, List[str]]:
    """Column names per table, read back from the generated CREATE TABLE blocks.

    The column list is not rebuilt from the model: fields can be skipped, and
    tables/joins/documents each add their own columns, so the emitted SQL is
    the only accurate source.
    """
    columns = {}
    for table_name, body in re.findall(
        r'CREATE TABLE "([^"]+)" \(\n(.*?)\n\s*\);', schema_sql, re.DOTALL
    ):
        # Constraint lines (UNIQUE, FOREIGN KEY, CONSTRAINT ...) never start with a quote.
        columns[table_name] = [
            match.group(1)
            for match in (re.match(r'\s*"([^"]+)"\s', line) for line in body.splitlines())
            if match
        ]
    return columns


def generate_id_insert_privileges(schema_sql: str, tables: List[Any]) -> List[str]:
    """Remove API roles' ability to provide an explicit SERIAL primary key.

    Supabase's default table grants include INSERT. PostgreSQL table-level
    INSERT implies INSERT on every column, so a column-level REVOKE alone is
    ineffective: the table grant has to go and come back as a column list
    without ``id``. Plain statements (rather than a DO block reading the
    catalog) stay re-runnable and remain visible to the production schema
    diff. Database owners and trusted direct connections are not affected.
    """
    table_columns = _created_table_columns(schema_sql)
    sql_parts = []
    for table in tables:
        name = _table_name(table)
        insert_columns = [column for column in table_columns.get(name, []) if column != "id"]
        if not insert_columns:
            raise ValueError(
                f"Cannot narrow INSERT on '{name}': no non-id columns found in its CREATE TABLE"
            )
        column_list = ", ".join(f'"{column}"' for column in insert_columns)
        sql_parts.append(f"""
REVOKE INSERT ON TABLE "{name}" FROM {API_ROLES};
GRANT INSERT ({column_list}) ON TABLE "{name}" TO {API_ROLES};
""")
    return sql_parts


def generate_system_timestamp_triggers(tables: List[Any]) -> List[str]:
    sql_parts = [f"""
CREATE OR REPLACE FUNCTION "{SET_SYSTEM_TIMESTAMPS_FUNCTION}"()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        NEW."_created_at" := CURRENT_TIMESTAMP;
        NEW."_updated_at" := CURRENT_TIMESTAMP;
    ELSIF (TG_OP = 'UPDATE') THEN
        NEW."_updated_at" := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""]

    for table in tables:
        table_name = _table_name(table)
        sql_parts.append(f"""
DROP TRIGGER IF EXISTS "{SET_SYSTEM_TIMESTAMPS_TRIGGER}" ON "{table_name}";
CREATE TRIGGER "{SET_SYSTEM_TIMESTAMPS_TRIGGER}"
BEFORE INSERT OR UPDATE ON "{table_name}"
FOR EACH ROW
EXECUTE FUNCTION "{SET_SYSTEM_TIMESTAMPS_FUNCTION}"();
""")

    return sql_parts
