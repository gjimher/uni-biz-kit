from typing import Any, Dict, List


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
