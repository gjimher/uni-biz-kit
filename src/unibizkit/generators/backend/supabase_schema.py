from .context import Context
from .schema_parts.tables import generate_table_sql
from .schema_parts.joins import generate_join_tables, generate_foreign_key_constraints, get_join_table_names
from .schema_parts.documents import generate_document_tables
from .schema_parts.internal_columns import generate_internal_column_protection, generate_system_timestamp_triggers
from .schema_parts.triggers import generate_presentation_triggers, generate_rollup_triggers
from .schema_parts.security import generate_security_policies


def _generated_table_names(ctx: Context) -> list[str]:
    table_names = [concept["name"] for concept in ctx.concepts]
    table_names.extend(get_join_table_names(ctx.concepts, ctx.concept_map))
    table_names.extend(
        f"{concept['name']}_document"
        for concept in ctx.concepts
        if concept["documents"]["enabled"]
    )
    return table_names


def generate(ctx: Context) -> str:
    sql_parts = []

    sql_parts.append("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    for concept in ctx.concepts:
        sql_parts.append(generate_table_sql(concept))

    sql_parts.extend(generate_join_tables(ctx.concepts, ctx.concept_map))
    sql_parts.extend(generate_foreign_key_constraints(ctx.concepts, ctx.security_config))
    sql_parts.extend(generate_document_tables(ctx.concepts, ctx.security_config, ctx.business_schema.get("_concept_workflow", {})))

    generated_table_names = _generated_table_names(ctx)
    sql_parts.extend(generate_internal_column_protection(generated_table_names))
    sql_parts.extend(generate_system_timestamp_triggers(generated_table_names))

    sql_parts.extend(generate_rollup_triggers(ctx.concepts, ctx.concept_map))
    sql_parts.extend(generate_presentation_triggers(ctx.concepts))

    if ctx.security_config["authentication_required"]:
        sql_parts.extend(generate_security_policies(
            ctx.concepts, ctx.concept_map, ctx.security_config, ctx.business_schema
        ))

    return '\n\n'.join(sql_parts)
