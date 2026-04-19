from .context import Context
from .schema_parts.tables import generate_table_sql
from .schema_parts.joins import generate_join_tables, generate_foreign_key_constraints
from .schema_parts.documents import generate_document_tables
from .schema_parts.triggers import generate_presentation_triggers
from .schema_parts.security import generate_security_policies


def generate(ctx: Context) -> str:
    sql_parts = []

    sql_parts.append("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    sql_parts.append("""
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW."_updated_at" = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

    for concept in ctx.concepts:
        sql_parts.append(generate_table_sql(concept))

    sql_parts.extend(generate_join_tables(ctx.concepts, ctx.concept_map))
    sql_parts.extend(generate_foreign_key_constraints(ctx.concepts))
    sql_parts.extend(generate_document_tables(ctx.concepts, ctx.security_config))
    sql_parts.extend(generate_presentation_triggers(ctx.concepts))

    if ctx.security_config["authentication_required"]:
        sql_parts.extend(generate_security_policies(
            ctx.concepts, ctx.concept_map, ctx.security_config, ctx.business_schema
        ))

    return '\n\n'.join(sql_parts)
