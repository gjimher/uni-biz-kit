import re
from typing import Any, Dict, List

_ROLLUP_SQL_FUNCS = {'sum': 'SUM', 'count': 'COUNT', 'avg': 'AVG', 'min': 'MIN', 'max': 'MAX'}


def _parse_rollup(expr: str):
    m = re.match(r'^rollup\((\w+),(\w+),(\w+)\)$', expr.replace(' ', ''))
    if not m:
        raise ValueError(f"Invalid rollup expression: {expr!r}. Expected rollup(func,child_concept,child_field)")
    return m.group(1), m.group(2), m.group(3)


def generate_rollup_triggers(concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]) -> List[str]:
    triggers = []

    for concept in concepts:
        parent_name = concept["name"]
        for field in concept["fields"]:
            if 'calculated' not in field:
                continue
            expr = field["calculated"]
            if not expr.startswith('rollup('):
                continue

            func, child_concept_name, child_field_name = _parse_rollup(expr)
            rollup_field_name = field["name"]

            if child_concept_name not in concept_map:
                raise ValueError(
                    f"Rollup '{parent_name}.{rollup_field_name}': child concept '{child_concept_name}' not found"
                )

            child_concept = concept_map[child_concept_name]
            fk_field_name = None
            for cf in child_concept["fields"]:
                if (cf["type"] == "relation_to_one"
                        and cf.get("subtype") == "part_of"
                        and cf["target"] == parent_name):
                    fk_field_name = cf["name"]
                    break

            if fk_field_name is None:
                raise ValueError(
                    f"Rollup '{parent_name}.{rollup_field_name}': '{child_concept_name}' is not part_of '{parent_name}'"
                )

            if not any(cf["name"] == child_field_name for cf in child_concept["fields"]):
                raise ValueError(
                    f"Rollup '{parent_name}.{rollup_field_name}': field '{child_field_name}' not found in '{child_concept_name}'"
                )

            sql_func = _ROLLUP_SQL_FUNCS.get(func.lower())
            if sql_func is None:
                raise ValueError(
                    f"Rollup '{parent_name}.{rollup_field_name}': unsupported function '{func}'. "
                    f"Supported: {list(_ROLLUP_SQL_FUNCS)}"
                )

            sql_type = field["_be_sql_type"]
            fn_name = f"rollup_{child_concept_name}_{parent_name}_{rollup_field_name}"
            trigger_name = f"{child_concept_name}_rollup_{rollup_field_name}"

            protect_fn = f"protect_{parent_name}_{rollup_field_name}"
            protect_trigger = f"{parent_name}_protect_{rollup_field_name}"

            trigger_sql = f"""
CREATE OR REPLACE FUNCTION "{fn_name}"()
RETURNS TRIGGER AS $$
DECLARE
    parent_id INTEGER;
    rollup_value {sql_type};
BEGIN
    IF TG_OP = 'DELETE' THEN
        parent_id := OLD."{fk_field_name}";
    ELSE
        parent_id := NEW."{fk_field_name}";
    END IF;

    IF TG_OP = 'UPDATE' AND OLD."{fk_field_name}" IS DISTINCT FROM NEW."{fk_field_name}" THEN
        SELECT COALESCE({sql_func}("{child_field_name}"), 0) INTO rollup_value
        FROM "{child_concept_name}" WHERE "{fk_field_name}" = OLD."{fk_field_name}";
        UPDATE "{parent_name}" SET "{rollup_field_name}" = rollup_value WHERE "id" = OLD."{fk_field_name}";
    END IF;

    SELECT COALESCE({sql_func}("{child_field_name}"), 0) INTO rollup_value
    FROM "{child_concept_name}" WHERE "{fk_field_name}" = parent_id;
    UPDATE "{parent_name}" SET "{rollup_field_name}" = rollup_value WHERE "id" = parent_id;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "{trigger_name}"
AFTER INSERT OR UPDATE OR DELETE ON "{child_concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_name}"();

CREATE OR REPLACE FUNCTION "{protect_fn}"()
RETURNS TRIGGER AS $$
DECLARE
    rollup_value {sql_type};
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW."{rollup_field_name}" := 0;
    ELSE
        SELECT COALESCE({sql_func}("{child_field_name}"), 0) INTO rollup_value
        FROM "{child_concept_name}" WHERE "{fk_field_name}" = NEW.id;
        NEW."{rollup_field_name}" := rollup_value;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "{protect_trigger}"
BEFORE INSERT OR UPDATE ON "{parent_name}"
FOR EACH ROW EXECUTE FUNCTION "{protect_fn}"();
"""
            triggers.append(trigger_sql)

    return triggers


def generate_presentation_triggers(concepts: List[Dict[str, Any]]) -> List[str]:
    triggers = []

    for concept in concepts:
        presentation_config = concept["id_presentation"]
        if 'fields' not in presentation_config:
            continue

        presentation_fields = presentation_config["fields"]
        if not presentation_fields:
            continue

        is_complex = any('.' in f for f in presentation_fields)
        if not is_complex:
            continue

        table_name = concept["name"]
        declarations = []
        selects = []
        parts = []

        for idx, field_name in enumerate(presentation_fields):
            part_var = f"part_{idx}"

            if '.' in field_name:
                rel_name, target_field = field_name.split('.', 1)

                rel = None
                for f in concept["fields"]:
                    if f["type"] == "relation_to_one" and f["name"] == rel_name:
                        rel = {
                            'type': 'belongs-to',
                            'field_name': f["name"],
                            'target': f["target"]
                        }
                        break

                if rel:
                    fk_col = rel.get("field_name", f"{rel['target']}_id")
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
                if field_name == "id":
                    parts.append(f"""COALESCE(NEW."id"::TEXT, '')""")
                else:
                    field_exists = any(f["name"] == field_name for f in concept["fields"])
                    if field_exists:
                        parts.append(f"""COALESCE(NEW."{field_name}"::TEXT, '')""")
                    else:
                        parts.append("''")

        separator = presentation_config["separator"]
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
