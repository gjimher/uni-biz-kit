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

    for concept in _sort_concepts_for_seed_data(ctx):
        visit(concept["name"])

    sql_parts = []
    user_directory_seed = _generate_user_directory_seed(ctx)
    if user_directory_seed:
        sql_parts.append(user_directory_seed)

    seed_data = _generate_seed_data(ctx)
    if seed_data:
        sql_parts.append(seed_data)

    if ctx.seed_data_config["include_test_data"]:
        for concept in sorted_concepts:
            if concept["name"].startswith("_"):
                continue
            profile_seed_data = _generate_profile_seed_data_for_concept(concept, ctx)
            if profile_seed_data:
                sql_parts.append(profile_seed_data)

            sample_data = _generate_sample_data_for_concept(concept, ctx)
            if sample_data:
                sql_parts.append(sample_data)

    return '\n\n'.join(sql_parts)


def _generate_user_directory_seed(ctx: Context) -> str:
    """Seed the _user_directory discovery cache with the model-defined users.

    Runs before auth users exist, so _user stays NULL until each user's first
    login (the access token hook upserts the row with the real auth uuid).
    """
    if not ctx.workflow_config["_concept_workflow"]:
        return ""
    if not ctx.security_config["authentication_required"]:
        return ""

    rows = []
    for user in ctx.security_config["users"]:
        email = user["email"].lower()
        roles_json = ",".join(f'"{role}"' for role in user["roles"])
        rows.append(
            f"({_sql_literal(email)}, '[{roles_json}]'::jsonb, 'seed')"
        )
    if not rows:
        return ""
    return (
        "-- _user_directory discovery cache: model-defined users\n"
        'INSERT INTO "_user_directory" ("email", "roles", "source") VALUES\n'
        + ",\n".join(rows)
        + '\nON CONFLICT ("email") DO NOTHING;'
    )


def _profile_role_for_concept(concept_name: str, ctx: Context) -> str:
    for mapping in ctx.security_config["_profile_concepts"]:
        if mapping["concept"] == concept_name:
            return mapping["role"]
    return ""


def _generate_profile_seed_data_for_concept(concept: Dict[str, Any], ctx: Context) -> str:
    role_name = _profile_role_for_concept(concept["name"], ctx)
    if not role_name:
        return ""

    users = [
        user for user in ctx.security_config["users"]
        if role_name in user["roles"]
    ]
    if not users:
        return ""

    rows = [
        f"({_sql_literal(user['email'])})"
        for user in users
    ]
    return (
        f'INSERT INTO "{concept["name"]}" ("_user_pending_link") VALUES\n'
        + ",\n".join(rows)
        + '\nON CONFLICT ("_user_pending_link") DO NOTHING;'
    )


def _generate_sample_data_for_concept(concept: Dict[str, Any], ctx: Context) -> str:
    table_name = concept["name"]
    data_size = concept["data_size"]
    num_records_by_data_size = lambda ds: 100 if ds == "m" else 10
    num_records = num_records_by_data_size(data_size)

    sample_records = []

    for i in range(1, num_records + 1):
        field_values = []
        field_names = []

        if concept.get("_integration_target"):
            field_names.append("_external_id")
            field_values.append(f"'sample:{table_name}:{i}'")

        for field in concept["fields"]:
            field_name = field["name"]
            field_type = field["type"]

            if field_name.startswith("_"):
                continue

            if 'calculated' in field or field["_be_sql_type"] == "SERIAL":
                continue

            if field["name"] in ("state_info", "state_task_owner"):
                continue

            if field_type == "string":
                if field_name == "email":
                    value = f"'{table_name}_{field_name}_{i}@example.com'"
                elif field_name == "state":
                    concept_workflow = ctx.workflow_config["_concept_workflow"].get(table_name)
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

        fields_str = ', '.join([f'"{field_name}"' for field_name in field_names])
        values_str = ', '.join(field_values)
        sample_records.append(f"({values_str})")

    if not sample_records:
        return ""

    return f'INSERT INTO "{table_name}" ({fields_str}) VALUES\n' + ",\n".join(sample_records) + ";"


def _generate_seed_data(ctx: Context) -> str:
    seed_data = ctx.seed_data_config
    records_by_concept = seed_data["records"]
    if not records_by_concept:
        return ""

    sql_parts = [
        "-- Model-defined seed data",
        "CREATE TEMP TABLE unibizkit_seed_data_ids (concept TEXT NOT NULL, seed_key TEXT NOT NULL, db_id INTEGER NOT NULL) ON COMMIT PRESERVE ROWS;"
    ]
    many_to_many_rows = []

    for concept in _sort_concepts_for_seed_data(ctx):
        concept_name = concept["name"]
        records = records_by_concept.get(concept_name, [])
        if not records:
            continue

        field_map = {field["name"]: field for field in concept["fields"]}
        scalar_rows = []

        for index, record in enumerate(records, start=1):
            seed_key = _record_seed_key(concept_name, record, index)
            columns = []
            values = []

            for field_name, value in record.items():
                if field_name in ("id", "documents"):
                    continue
                if field_name not in field_map:
                    raise ValueError(f"Unknown field '{field_name}' in seed data for concept '{concept_name}'")

                field = field_map[field_name]
                if field["type"] == "relation_to_many":
                    if value is None:
                        continue
                    if not isinstance(value, list):
                        raise ValueError(
                            f"Seed data relation_to_many field '{concept_name}.{field_name}' must be a list of ids"
                        )
                    many_to_many_rows.extend(
                        _generate_many_to_many_rows(concept_name, field["target"], seed_key, value)
                    )
                    continue

                if 'calculated' in field or field["_be_sql_type"] == "SERIAL":
                    raise ValueError(f"Seed data cannot set generated field '{concept_name}.{field_name}'")

                columns.append(field_name)
                values.append(_sql_value(value, field))

            if columns:
                fields_sql = ', '.join(f'"{column}"' for column in columns)
                values_sql = ', '.join(values)
                scalar_rows.append(
                    f'WITH inserted AS (\n'
                    f'  INSERT INTO "{concept_name}" ({fields_sql}) VALUES ({values_sql}) RETURNING "id"\n'
                    f')\n'
                    f"INSERT INTO unibizkit_seed_data_ids (concept, seed_key, db_id)\n"
                    f"SELECT {_sql_literal(concept_name)}, {_sql_literal(seed_key)}, id FROM inserted;"
                )
            else:
                scalar_rows.append(
                    f'WITH inserted AS (\n'
                    f'  INSERT INTO "{concept_name}" DEFAULT VALUES RETURNING "id"\n'
                    f')\n'
                    f"INSERT INTO unibizkit_seed_data_ids (concept, seed_key, db_id)\n"
                    f"SELECT {_sql_literal(concept_name)}, {_sql_literal(seed_key)}, id FROM inserted;"
                )

        sql_parts.extend(scalar_rows)

    if many_to_many_rows:
        sql_parts.extend(many_to_many_rows)

    return "\n".join(sql_parts)


def _record_seed_key(concept_name: str, record: Dict[str, Any], index: int) -> str:
    if "id" in record:
        return str(record["id"])
    return f"__{concept_name}_{index}"


def _sort_concepts_for_seed_data(ctx: Context) -> List[Dict[str, Any]]:
    sorted_concepts = []
    visited = set()

    def visit(concept: Dict[str, Any]):
        concept_name = concept["name"]
        if concept_name in visited:
            return
        visited.add(concept_name)
        for field in concept["fields"]:
            if field["type"] == "relation_to_one" and field["target"] != concept_name:
                target_concept = ctx.concept_map.get(field["target"])
                if target_concept:
                    visit(target_concept)
        sorted_concepts.append(concept)

    for concept in ctx.concepts:
        visit(concept)

    return sorted_concepts


def _generate_many_to_many_rows(concept_name: str, target_name: str, seed_key: str, target_ids: List[Any]) -> List[str]:
    join_table = f"{min(concept_name, target_name)}_{max(concept_name, target_name)}"
    rows = []
    for target_id in target_ids:
        rows.append(
            f'INSERT INTO "{join_table}" ("{concept_name}_id", "{target_name}_id") '
            f"VALUES ({_seed_id_subquery(concept_name, seed_key)}, {_seed_id_subquery(target_name, target_id)}) "
            f"ON CONFLICT DO NOTHING;"
        )
    return rows


def _sql_value(value: Any, field: Dict[str, Any]) -> str:
    if field["type"] == "relation_to_one" and value is not None:
        return _seed_id_subquery(field["target"], value)
    return _sql_literal(value)


def _seed_id_subquery(concept_name: str, seed_key: Any) -> str:
    return (
        "(SELECT db_id FROM unibizkit_seed_data_ids "
        f"WHERE concept = {_sql_literal(concept_name)} AND seed_key = {_sql_literal(str(seed_key))})"
    )


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    raise ValueError(f"Unsupported seed data value type: {type(value).__name__}")
