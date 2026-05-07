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


def _parse_copy(expr: str):
    """Parse copy(fk_field,source_field,when) -> (fk_field, source_field, [events])."""
    m = re.match(r'^copy\((\w+),(\w+),([\w+]+)\)$', expr.replace(' ', ''))
    if not m:
        raise ValueError(f"Invalid copy expression: {expr!r}. Expected copy(fk_field,source_field,when)")
    fk_field = m.group(1)
    source_field = m.group(2)
    when_str = m.group(3)
    if when_str == 'always':
        return fk_field, source_field, ['always']
    events = when_str.split('+')
    for event in events:
        if event != 'on_insert' and not event.startswith('state_'):
            raise ValueError(
                f"Invalid event '{event}' in copy expression. "
                "Expected 'always', 'on_insert', or 'state_<name>'"
            )
    return fk_field, source_field, events


def _parse_copy_logged_on_insert(expr: str):
    """Parse copy_logged_on_insert(fk_field) -> fk_field."""
    m = re.match(r'^copy_logged_on_insert\((\w+)\)$', expr.replace(' ', ''))
    if not m:
        raise ValueError(
            f"Invalid copy_logged_on_insert expression: {expr!r}. "
            "Expected copy_logged_on_insert(fk_field)"
        )
    return m.group(1)


def generate_copy_triggers(
    concepts: List[Dict[str, Any]],
    concept_map: Dict[str, Any],
    security_config: Dict[str, Any],
) -> List[str]:
    triggers = []
    profile_concept_names = {m["concept"] for m in security_config.get("_profile_concepts", [])}

    for concept in concepts:
        concept_name = concept["name"]

        # Find the part_of parent (for state event resolution when concept has no workflow).
        parent_concept_name = None
        parent_fk_col = None
        for f in concept["fields"]:
            if f["type"] == "relation_to_one" and f.get("subtype") == "part_of":
                parent_concept_name = f["target"]
                parent_fk_col = f["name"]
                break

        concept_has_workflow = any(f["name"] == "state" for f in concept["fields"])

        for field in concept["fields"]:
            if "calculated" not in field:
                continue
            expr = field["calculated"]
            field_name = field["name"]

            # ── copy(fk_field, source_field, when) ──────────────────────────
            if expr.startswith("copy("):
                fk_field, source_field, events = _parse_copy(expr)

                fk_def = next((f for f in concept["fields"] if f["name"] == fk_field), None)
                if fk_def is None:
                    raise ValueError(
                        f"copy field '{concept_name}.{field_name}': "
                        f"FK field '{fk_field}' not found in '{concept_name}'"
                    )
                if fk_def["type"] != "relation_to_one":
                    raise ValueError(
                        f"copy field '{concept_name}.{field_name}': "
                        f"'{fk_field}' is not a relation_to_one field"
                    )
                fk_target = fk_def["target"]

                if fk_target not in concept_map:
                    raise ValueError(
                        f"copy field '{concept_name}.{field_name}': "
                        f"target concept '{fk_target}' not found"
                    )
                if not any(f["name"] == source_field for f in concept_map[fk_target]["fields"]):
                    raise ValueError(
                        f"copy field '{concept_name}.{field_name}': "
                        f"source field '{source_field}' not found in '{fk_target}'"
                    )

                has_on_insert = "on_insert" in events or "always" in events
                has_always = "always" in events

                # BEFORE INSERT: copy from FK based on applicable events.
                parent_state_events = [
                    e[len("state_"):] for e in events
                    if e.startswith("state_") and not concept_has_workflow
                ]

                insert_declare = ""
                if has_on_insert:
                    insert_body = (
                        f'\n    IF NEW."{fk_field}" IS NOT NULL THEN\n'
                        f'        SELECT "{source_field}" INTO NEW."{field_name}" '
                        f'FROM "{fk_target}" WHERE "id" = NEW."{fk_field}";\n'
                        f'    ELSE\n'
                        f'        NEW."{field_name}" := NULL;\n'
                        f'    END IF;'
                    )
                elif parent_state_events and parent_concept_name:
                    # Check the parent's current state; copy only when it matches.
                    state_list = ", ".join(f"'{s}'" for s in parent_state_events)
                    insert_declare = "DECLARE\n    v_parent_state TEXT;\n"
                    insert_body = (
                        f'\n    NEW."{field_name}" := NULL;\n'
                        f'    IF NEW."{parent_fk_col}" IS NOT NULL THEN\n'
                        f'        SELECT "state" INTO v_parent_state\n'
                        f'        FROM "{parent_concept_name}" WHERE "id" = NEW."{parent_fk_col}";\n'
                        f'        IF v_parent_state IN ({state_list}) THEN\n'
                        f'            IF NEW."{fk_field}" IS NOT NULL THEN\n'
                        f'                SELECT "{source_field}" INTO NEW."{field_name}"\n'
                        f'                FROM "{fk_target}" WHERE "id" = NEW."{fk_field}";\n'
                        f'            END IF;\n'
                        f'        END IF;\n'
                        f'    END IF;'
                    )
                else:
                    insert_body = f'\n    NEW."{field_name}" := NULL;'

                fn_ins = f"copy_on_insert_{concept_name}_{field_name}"
                tg_ins = f"{concept_name}_copy_on_insert_{field_name}"
                triggers.append(f"""
CREATE OR REPLACE FUNCTION "{fn_ins}"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
{insert_declare}BEGIN{insert_body}
    RETURN NEW;
END;
$$;

CREATE TRIGGER "{tg_ins}"
BEFORE INSERT ON "{concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_ins}"();""")

                # BEFORE UPDATE: protect or recopy when FK changes in a matching state.
                update_declare = ""
                if has_always:
                    update_body = (
                        f'\n    IF NEW."{fk_field}" IS NOT NULL THEN\n'
                        f'        SELECT "{source_field}" INTO NEW."{field_name}" '
                        f'FROM "{fk_target}" WHERE "id" = NEW."{fk_field}";\n'
                        f'    ELSE\n'
                        f'        NEW."{field_name}" := NULL;\n'
                        f'    END IF;'
                    )
                elif parent_state_events and parent_concept_name:
                    # Recopy when FK changes and parent state matches; else protect.
                    state_list = ", ".join(f"'{s}'" for s in parent_state_events)
                    update_declare = "DECLARE\n    v_parent_state TEXT;\n"
                    update_body = (
                        f'\n    IF pg_trigger_depth() = 1 THEN\n'
                        f'        IF NEW."{fk_field}" IS DISTINCT FROM OLD."{fk_field}" THEN\n'
                        f'            SELECT "state" INTO v_parent_state\n'
                        f'            FROM "{parent_concept_name}" WHERE "id" = NEW."{parent_fk_col}";\n'
                        f'            IF v_parent_state IN ({state_list}) THEN\n'
                        f'                IF NEW."{fk_field}" IS NOT NULL THEN\n'
                        f'                    SELECT "{source_field}" INTO NEW."{field_name}"\n'
                        f'                    FROM "{fk_target}" WHERE "id" = NEW."{fk_field}";\n'
                        f'                ELSE\n'
                        f'                    NEW."{field_name}" := NULL;\n'
                        f'                END IF;\n'
                        f'            ELSE\n'
                        f'                NEW."{field_name}" := OLD."{field_name}";\n'
                        f'            END IF;\n'
                        f'        ELSE\n'
                        f'            NEW."{field_name}" := OLD."{field_name}";\n'
                        f'        END IF;\n'
                        f'    END IF;'
                    )
                else:
                    update_body = (
                        f'\n    IF pg_trigger_depth() = 1 THEN\n'
                        f'        NEW."{field_name}" := OLD."{field_name}";\n'
                        f'    END IF;'
                    )

                fn_upd = f"protect_update_{concept_name}_{field_name}"
                tg_upd = f"{concept_name}_protect_update_{field_name}"
                triggers.append(f"""
CREATE OR REPLACE FUNCTION "{fn_upd}"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
{update_declare}BEGIN{update_body}
    RETURN NEW;
END;
$$;

CREATE TRIGGER "{tg_upd}"
BEFORE UPDATE ON "{concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_upd}"();""")

                # State-transition triggers.
                for event in events:
                    if not event.startswith("state_"):
                        continue
                    state_name = event[len("state_"):]

                    fn_st = f"copy_state_{concept_name}_{field_name}_{state_name}"

                    if concept_has_workflow:
                        tg_st = f"{concept_name}_copy_state_{field_name}_{state_name}"
                        triggers.append(f"""
CREATE OR REPLACE FUNCTION "{fn_st}"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW."state" = '{state_name}' AND (TG_OP = 'INSERT' OR OLD."state" IS DISTINCT FROM NEW."state") THEN
        IF NEW."{fk_field}" IS NOT NULL THEN
            SELECT "{source_field}" INTO NEW."{field_name}" FROM "{fk_target}" WHERE "id" = NEW."{fk_field}";
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "{tg_st}"
BEFORE INSERT OR UPDATE OF "state" ON "{concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_st}"();""")

                    else:
                        if parent_concept_name is None:
                            raise ValueError(
                                f"copy field '{concept_name}.{field_name}': event '{event}' "
                                f"requires a workflow, but '{concept_name}' has no workflow "
                                "and no part_of parent"
                            )
                        tg_st = f"{parent_concept_name}_copy_{concept_name}_{field_name}_state_{state_name}"
                        triggers.append(f"""
CREATE OR REPLACE FUNCTION "{fn_st}"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW."state" = '{state_name}' AND (TG_OP = 'INSERT' OR OLD."state" IS DISTINCT FROM NEW."state") THEN
        UPDATE "{concept_name}"
        SET "{field_name}" = (
            SELECT t."{source_field}" FROM "{fk_target}" t WHERE t."id" = "{concept_name}"."{fk_field}"
        )
        WHERE "{parent_fk_col}" = NEW."id"
          AND "{concept_name}"."{fk_field}" IS NOT NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "{tg_st}"
AFTER INSERT OR UPDATE OF "state" ON "{parent_concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_st}"();""")

            # ── copy_logged_on_insert(fk_field) ─────────────────────────────
            elif expr.startswith("copy_logged_on_insert("):
                fk_arg = _parse_copy_logged_on_insert(expr)

                fk_def = next((f for f in concept["fields"] if f["name"] == fk_arg), None)
                if fk_def is None:
                    raise ValueError(
                        f"copy_logged_on_insert field '{concept_name}.{field_name}': "
                        f"FK field '{fk_arg}' not found in '{concept_name}'"
                    )
                if fk_def["type"] != "relation_to_one":
                    raise ValueError(
                        f"copy_logged_on_insert field '{concept_name}.{field_name}': "
                        f"'{fk_arg}' is not a relation_to_one field"
                    )
                profile_name = fk_def["target"]
                if profile_name not in profile_concept_names:
                    raise ValueError(
                        f"copy_logged_on_insert field '{concept_name}.{field_name}': "
                        f"'{profile_name}' is not a profile concept"
                    )

                fn_ins = f"copy_logged_on_insert_{concept_name}_{field_name}"
                tg_ins = f"{concept_name}_copy_logged_on_insert_{field_name}"
                triggers.append(f"""
CREATE OR REPLACE FUNCTION "{fn_ins}"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW."{field_name}" := NULL;
    IF auth.uid() IS NOT NULL THEN
        SELECT "id" INTO NEW."{field_name}" FROM "{profile_name}" WHERE "_user" = auth.uid();
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "{tg_ins}"
BEFORE INSERT ON "{concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_ins}"();""")

                fn_upd = f"protect_update_{concept_name}_{field_name}"
                tg_upd = f"{concept_name}_protect_update_{field_name}"
                triggers.append(f"""
CREATE OR REPLACE FUNCTION "{fn_upd}"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() = 1 THEN
        NEW."{field_name}" := OLD."{field_name}";
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER "{tg_upd}"
BEFORE UPDATE ON "{concept_name}"
FOR EACH ROW EXECUTE FUNCTION "{fn_upd}"();""")

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
