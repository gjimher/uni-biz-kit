import json
from ..context import Context
from .resources.helpers import build_m2m_config


def generate(ctx: Context) -> str:
    m2m_config = build_m2m_config(ctx.concepts, ctx.concept_map)

    config = {}
    for concept in ctx.concepts:
        name = concept["name"]

        fields = []
        for field in concept["fields"]:
            if field["_fe_visibility"] != "editable":
                continue
            if field["type"] in ("relation_to_many", "prefill"):
                continue
            entry = {
                'name': field["name"],
                'type': field["type"],
                'required': field["_be_not_null"],
            }
            if field["type"] == "enum":
                entry['values'] = field["enum_values"]
            if field["type"] == "relation_to_one":
                entry['target'] = field["target"]
            fields.append(entry)

        documents = None
        docs = concept["documents"]
        if docs["enabled"] and docs.get("tags"):
            documents = {
                'bucket': f"{name}-documents",
                'table': f"{name}_document",
                'fkCol': f"{name}_id",
                'versioned': docs["versioned"],
                'tags': docs["tags"],
            }

        config[name] = {
            'fields': fields,
            'm2m': m2m_config.get(name, {}),
            'documents': documents,
        }

    config_json = json.dumps(config, indent=2)

    return f"""// CSV export/import configuration, one entry per concept.
// fields: editable scalar/FK columns (never id, id_presentation, calculated or internal fields).
// m2m: many-to-many links resolved through join tables.
// documents: Storage bucket and metadata table for base64 document columns, or null.
export const IMPORT_EXPORT_CONFIG = {config_json};
"""
