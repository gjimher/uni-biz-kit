from typing import Any, Dict, List


def generate_table_sql(concept: Dict[str, Any]) -> str:
    table_name = concept["name"]
    pk_name = "id"

    sql_lines = [f'CREATE TABLE "{table_name}" (']
    sql_lines.append(f'  "{pk_name}" SERIAL PRIMARY KEY,')

    for field in concept["fields"]:
        field_sql = generate_field_sql(field, concept)
        if field_sql:
            sql_lines.append(f"  {field_sql},")

    presentation_mode = concept["_be_presentation_mode"]
    if presentation_mode == "generated_column":
        expr = concept["_be_presentation_expr"]
        sql_lines.append(f'  "id_presentation" TEXT GENERATED ALWAYS AS ({expr}) STORED,')
    elif presentation_mode == "trigger":
        sql_lines.append(f'  "id_presentation" TEXT,')

    sql_lines.append('  "_created_at" TIMESTAMP WITH TIME ZONE,')
    sql_lines.append('  "_updated_at" TIMESTAMP WITH TIME ZONE')
    sql_lines.append(');')

    checks = concept.get('checks', [])
    for i, check_expr in enumerate(checks):
        constraint_name = f"{table_name}_check_{i}"
        sql_lines.append(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" CHECK ({check_expr});')

    unique_fields = [field for field in concept["fields"] if field["unique"]]
    for field in unique_fields:
        field_name = field["name"]
        constraint_name = f"{table_name}_{field_name}_unique"
        sql_lines.append(f'CREATE UNIQUE INDEX "{constraint_name}" ON "{table_name}" ("{field_name}");')

    return '\n'.join(sql_lines)


def generate_field_sql(field: Dict[str, Any], concept: Dict[str, Any]) -> str:
    field_name = field["name"]
    sql_type = field["_be_sql_type"]

    if not sql_type:
        return ""

    if 'calculated' in field:
        expr = field["calculated"]
        if expr.startswith('rollup('):
            field_parts = [f'"{field_name}" {sql_type}']
            if field["_be_not_null"]:
                field_parts.append("NOT NULL")
            return ' '.join(field_parts)
        if expr.startswith('copy(') or expr.startswith('copy_logged_on_insert('):
            return f'"{field_name}" {sql_type}'
        sql_parts = [f'"{field_name}" {sql_type} GENERATED ALWAYS AS ({expr}) STORED']
        return ' '.join(sql_parts)

    field_parts = [f'"{field_name}" {sql_type}']

    if field["_be_not_null"]:
        field_parts.append("NOT NULL")

    if 'default' in field:
        default_value = field["default"]
        if isinstance(default_value, str):
            if default_value in ("auth.uid()", "auth.uid()::text"):
                field_parts.append(f"DEFAULT {default_value}")
            else:
                field_parts.append(f"DEFAULT '{default_value}'")
        elif isinstance(default_value, (int, float)):
            field_parts.append(f"DEFAULT {default_value}")
        elif isinstance(default_value, bool):
            field_parts.append(f"DEFAULT {str(default_value).upper()}")

    if field["type"] == "enum" and 'enum_values' in field:
        allowed_values = ', '.join([f"'{value}'" for value in field["enum_values"]])
        constraint_name = f"{field_name}_enum_check"
        field_parts.append(f"""CONSTRAINT "{constraint_name}" CHECK ("{field_name}" IN ({allowed_values}))""")

    return ' '.join(field_parts)
