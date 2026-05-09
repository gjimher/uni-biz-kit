from .context import Context
from .schema_parts.tables import generate_table_sql
from .schema_parts.joins import generate_join_tables, generate_foreign_key_constraints, get_join_table_names
from .schema_parts.documents import generate_document_tables
from .schema_parts.internal_columns import generate_internal_column_protection, generate_system_timestamp_triggers
from .schema_parts.triggers import generate_presentation_triggers, generate_rollup_triggers, generate_copy_triggers
from .schema_parts.security import generate_security_policies
from . import rules


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

    # Collect trigger-managed calculated columns per table for the 00_protect trigger.
    # SQL GENERATED ALWAYS AS columns are protected by PostgreSQL itself; only
    # rollup/copy/copy_logged_on_insert/by_rules need explicit listing.
    trigger_protected_cols: dict[str, list[str]] = {}
    for concept in ctx.concepts:
        cols = [
            f["name"] for f in concept["fields"]
            if "calculated" in f and (
                f["calculated"].startswith("rollup(")
                or f["calculated"].startswith("copy(")
                or f["calculated"].startswith("copy_logged_on_insert(")
                or f["calculated"] == "by_rules"
            )
        ]
        if cols:
            trigger_protected_cols[concept["name"]] = cols

    sql_parts.extend(generate_internal_column_protection(generated_table_names, trigger_protected_cols))
    sql_parts.extend(generate_system_timestamp_triggers(generated_table_names))

    sql_parts.extend(generate_rollup_triggers(ctx.concepts, ctx.concept_map))
    sql_parts.extend(generate_copy_triggers(ctx.concepts, ctx.concept_map, ctx.security_config))
    sql_parts.extend(generate_presentation_triggers(ctx.concepts))
    sql_parts.extend(rules.generate_async_rule_execution_sql(ctx))

    if ctx.security_config["authentication_required"]:
        sql_parts.extend(generate_security_policies(
            ctx.concepts, ctx.concept_map, ctx.security_config, ctx.business_schema
        ))

    return '\n\n'.join(sql_parts)
