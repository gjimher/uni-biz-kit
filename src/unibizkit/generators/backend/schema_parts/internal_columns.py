from typing import Any, Dict, List, Optional


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

    -- Skip for service_role — edge functions write by_rules fields using service_role.
    claims := current_setting('request.jwt.claims', true)::jsonb;
    IF claims ->> 'role' = 'service_role' THEN
        RETURN NEW;
    END IF;

    new_row := to_jsonb(NEW);

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
        old_row := to_jsonb(OLD);

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
