from typing import Any, Dict, List


PROTECT_INTERNAL_COLUMNS_TRIGGER = "00_protect_internal_columns_trigger"
PROTECT_INTERNAL_COLUMNS_FUNCTION = "00_protect_internal_columns_trigger_function"
SET_SYSTEM_TIMESTAMPS_TRIGGER = "01_set_system_timestamps_trigger"
SET_SYSTEM_TIMESTAMPS_FUNCTION = "01_set_system_timestamps_trigger_function"


def _table_name(table: Any) -> str:
    if isinstance(table, dict):
        return table["name"]
    return table


def generate_internal_column_protection(tables: List[Any]) -> List[str]:
    sql_parts = [f"""
CREATE OR REPLACE FUNCTION "{PROTECT_INTERNAL_COLUMNS_FUNCTION}"()
RETURNS TRIGGER AS $$
DECLARE
    new_row JSONB;
    old_row JSONB;
    column_name TEXT;
BEGIN
    new_row := to_jsonb(NEW);

    IF TG_OP = 'INSERT' THEN
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
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""]

    for table in tables:
        table_name = _table_name(table)
        sql_parts.append(f"""
DROP TRIGGER IF EXISTS "{PROTECT_INTERNAL_COLUMNS_TRIGGER}" ON "{table_name}";
CREATE TRIGGER "{PROTECT_INTERNAL_COLUMNS_TRIGGER}"
BEFORE INSERT OR UPDATE ON "{table_name}"
FOR EACH ROW
EXECUTE FUNCTION "{PROTECT_INTERNAL_COLUMNS_FUNCTION}"();
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
