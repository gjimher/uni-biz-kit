from typing import Any, Dict, List


def generate_join_tables(concepts: List[Dict[str, Any]], concept_map: Dict[str, Any]) -> List[str]:
    join_tables = []

    for concept in concepts:
        for field in concept["fields"]:
            if field["type"] == "relation_to_many":
                target_concept_name = field["target"]
                target_concept = concept_map.get(target_concept_name)

                if not target_concept:
                    continue

                is_one_to_many = False
                for target_field in target_concept["fields"]:
                    if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                        is_one_to_many = True
                        break

                if not is_one_to_many:
                    table1 = concept["name"]
                    table2 = target_concept_name
                    join_table_name = f"{min(table1, table2)}_{max(table1, table2)}"

                    if join_table_name not in [jt.split('(')[0].strip() for jt in join_tables]:
                        sql = f"""
CREATE TABLE "{join_table_name}" (
  "{table1}_id" INTEGER NOT NULL,
  "{table2}_id" INTEGER NOT NULL,
  "_created_at" TIMESTAMP WITH TIME ZONE,
  "_updated_at" TIMESTAMP WITH TIME ZONE,
  PRIMARY KEY ("{table1}_id", "{table2}_id"),
  FOREIGN KEY ("{table1}_id") REFERENCES "{table1}"("id") ON DELETE CASCADE,
  FOREIGN KEY ("{table2}_id") REFERENCES "{table2}"("id") ON DELETE CASCADE
);
"""
                        join_tables.append(sql)

    return join_tables


def generate_foreign_key_constraints(concepts: List[Dict[str, Any]]) -> List[str]:
    fk_constraints = []

    for concept in concepts:
        table_name = concept["name"]
        for field in concept["fields"]:
            if field["type"] == "relation_to_one":
                target_table = field["target"]
                field_name = field["name"]
                constraint_name = f"fk_{table_name}_{field_name}"
                fk_sql = f"""
ALTER TABLE "{table_name}"
  ADD CONSTRAINT "{constraint_name}"
  FOREIGN KEY ("{field_name}") REFERENCES "{target_table}"("id");"""
                fk_constraints.append(fk_sql)

    return fk_constraints
