from typing import Any, Dict, List
from .context import Context


def generate(ctx: Context) -> str:
    sorted_concepts = []
    visited = set()

    def visit(concept_name):
        if concept_name in visited:
            return
        concept = ctx.concept_map.get(concept_name)
        if not concept:
            return
        visited.add(concept_name)
        sorted_concepts.append(concept)

    for concept in ctx.concepts:
        visit(concept["name"])

    sql_parts = []
    for concept in sorted_concepts:
        sample_data = _generate_sample_data_for_concept(concept, ctx)
        if sample_data:
            sql_parts.append(sample_data)

    return '\n\n'.join(sql_parts)


def _generate_sample_data_for_concept(concept: Dict[str, Any], ctx: Context) -> str:
    table_name = concept["name"]
    data_size = concept["data_size"]
    num_records_by_data_size = lambda ds: 100 if ds == "m" else 10
    num_records = num_records_by_data_size(data_size)

    sample_records = []

    for i in range(1, num_records + 1):
        field_values = []
        field_names = []

        for field in concept["fields"]:
            field_name = field["name"]
            field_type = field["type"]

            if 'calculated' in field or field["_be_sql_type"] == "SERIAL":
                continue

            if field["name"] == "state_info":
                continue

            if field_type == "string":
                if field_name == "email":
                    value = f"'{table_name}_{field_name}_{i}@example.com'"
                elif field_name == "state":
                    concept_workflow = ctx.business_schema.get("_concept_workflow", {}).get(table_name)
                    if concept_workflow:
                        states = concept_workflow["states"]
                        value = f"'{states[(i - 1) % len(states)]['name']}'"
                    else:
                        value = f"'{table_name}_{field_name}_{i}'"
                else:
                    value = f"'{table_name}_{field_name}_{i}'"
            elif field_type == "integer":
                value = str(i * 10)
            elif field_type == "decimal":
                value = f"{i * 10}.{i:02d}"
            elif field_type == "boolean":
                value = 'TRUE' if i % 2 == 0 else 'FALSE'
            elif field_type == "enum":
                enum_values = field["enum_values"]
                val_idx = (i - 1) % len(enum_values)
                value = f"'{enum_values[val_idx]}'"
            elif field_type == "date":
                day = ((i - 1) % 28) + 1
                value = f"'2023-01-{day:02d}'"
            elif field_type == "datetime":
                day = ((i - 1) % 28) + 1
                value = f"'2023-01-{day:02d}T10:00:00Z'"
            elif field_type == "relation_to_one":
                target_concept_name = field["target"]
                if target_concept_name == concept["name"]:
                    if i <= 2:
                        value = "NULL"
                    else:
                        k = 1
                        while True:
                            level_start = 2 * (2**k - 1) + 1
                            level_end = 2 * (2**(k+1) - 1)
                            if level_start <= i <= level_end:
                                prev_level_start = 2 * (2**(k-1) - 1) + 1
                                parent_idx = (i - level_start) // 2 + prev_level_start
                                value = str(parent_idx)
                                break
                            k += 1
                            if k > 20:
                                value = "NULL"
                                break
                elif field.get("subtype") == "part_of":
                    p = 1
                    while (p * (p + 1)) // 2 < i:
                        p += 1
                    target_concept = ctx.concept_map.get(target_concept_name)
                    target_count = num_records_by_data_size(target_concept["data_size"]) if target_concept else 10
                    parent_id = ((p - 1) % target_count) + 1
                    value = str(parent_id)
                else:
                    target_concept = ctx.concept_map.get(target_concept_name)
                    if target_concept:
                        target_size = target_concept["data_size"]
                        target_count = num_records_by_data_size(target_size)
                        target_id = ((i - 1) % target_count) + 1
                        value = str(target_id)
                    else:
                        value = 'NULL'
            elif field_type == "relation_to_many":
                continue
            else:
                value = f"'{table_name}_{field_name}_{i}'"

            field_names.append(field_name)
            field_values.append(value)

        field_names.extend(['_created_at', '_updated_at'])
        field_values.extend(["'2023-01-01T10:00:00Z'", "'2023-01-01T10:00:00Z'"])

        fields_str = ', '.join([f'"{field_name}"' for field_name in field_names])
        values_str = ', '.join(field_values)
        sample_records.append(f"({values_str})")

    if not sample_records:
        return ""

    return f'INSERT INTO "{table_name}" ({fields_str}) VALUES\n' + ",\n".join(sample_records) + ";"
