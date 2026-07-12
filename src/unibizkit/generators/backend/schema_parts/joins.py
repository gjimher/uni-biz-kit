from typing import Any, Dict, Generator, List, Tuple


def _join_table_pairs(
    concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]
) -> Generator[Tuple[str, str, str], None, None]:
    """Yield (join_table_name, table1, table2) for each many-to-many join, deduplicated."""
    seen: set = set()
    for concept in concepts:
        for field in concept["fields"]:
            if field["type"] != "relation_to_many":
                continue
            target_concept = concept_map.get(field["target"])
            if not target_concept:
                continue
            is_one_to_many = any(
                f["type"] == "relation_to_one" and f["target"] == concept["name"]
                for f in target_concept["fields"]
            )
            if not is_one_to_many:
                table1 = concept["name"]
                table2 = field["target"]
                join_table_name = f"{min(table1, table2)}_{max(table1, table2)}"
                if join_table_name not in seen:
                    seen.add(join_table_name)
                    yield join_table_name, table1, table2


def get_join_table_names(concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]) -> List[str]:
    return [name for name, _, _ in _join_table_pairs(concepts, concept_map)]


def generate_join_tables(concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]) -> List[str]:
    join_tables = []
    for join_table_name, table1, table2 in _join_table_pairs(concepts, concept_map):
        join_tables.append(f"""
CREATE TABLE "{join_table_name}" (
  "{table1}_id" INTEGER NOT NULL,
  "{table2}_id" INTEGER NOT NULL,
  "_created_at" TIMESTAMP WITH TIME ZONE,
  "_updated_at" TIMESTAMP WITH TIME ZONE,
  PRIMARY KEY ("{table1}_id", "{table2}_id"),
  FOREIGN KEY ("{table1}_id") REFERENCES "{table1}"("id") ON DELETE CASCADE,
  FOREIGN KEY ("{table2}_id") REFERENCES "{table2}"("id") ON DELETE CASCADE
);
""")
    return join_tables


def _profile_concept_names(security_config: Dict[str, Any]) -> set[str]:
    return {mapping["concept"] for mapping in security_config["_profile_concepts"]}


def generate_foreign_key_constraints(
    concepts: List[Dict[str, Any]],
    security_config: Dict[str, Any],
) -> List[str]:
    fk_constraints = []
    profile_concepts = _profile_concept_names(security_config)

    for concept in concepts:
        table_name = concept["name"]
        for field in concept["fields"]:
            if field["type"] == "relation_to_one":
                target_table = field["target"]
                field_name = field["name"]
                constraint_name = f"fk_{table_name}_{field_name}"
                on_delete = {
                    "cascade": "CASCADE",
                    "set_null": "SET NULL",
                    "snapshot_data": "SET NULL",
                }[field["on_delete"]]
                is_part_of = field.get("subtype") == "part_of"
                if on_delete == "CASCADE" and target_table in profile_concepts and not is_part_of:
                    raise ValueError(
                        f'Concept "{table_name}" has required relation "{field_name}" '
                        f'to profile concept "{target_table}". Required relations use '
                        "ON DELETE CASCADE, which would prevent safe auth user deletion. "
                        "Make the relation optional or do not target a profile concept."
                    )
                fk_sql = f"""
ALTER TABLE "{table_name}"
  ADD CONSTRAINT "{constraint_name}"
  FOREIGN KEY ("{field_name}") REFERENCES "{target_table}"("id") ON DELETE {on_delete};"""
                fk_constraints.append(fk_sql)

    return fk_constraints


def generate_deleted_snapshot_triggers(concepts: List[Dict[str, Any]]) -> List[str]:
    """Snapshot referenced rows before ON DELETE SET NULL clears their foreign keys."""
    sql_parts = []
    for concept in concepts:
        referencing_table = concept["name"]
        for field in concept["fields"]:
            if field.get("on_delete") != "snapshot_data":
                continue
            field_name = field["name"]
            target_table = field["target"]
            snapshot_field = f"_{field_name}_deleted_snapshot"
            function_name = f"snapshot_{referencing_table}_{field_name}_before_delete"
            trigger_name = f"snapshot_{referencing_table}_{field_name}_before_delete_trigger"
            sql_parts.append(f'''
CREATE OR REPLACE FUNCTION "{function_name}"()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE "{referencing_table}"
  SET "{snapshot_field}" = to_jsonb(OLD)
  WHERE "{field_name}" = OLD."id";
  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

DROP TRIGGER IF EXISTS "{trigger_name}" ON "{target_table}";
CREATE TRIGGER "{trigger_name}"
BEFORE DELETE ON "{target_table}"
FOR EACH ROW
EXECUTE FUNCTION "{function_name}"();
''')
    return sql_parts
