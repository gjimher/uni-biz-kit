import json
from ...context import Context


def generate(ctx: Context) -> str:
    concepts = [
        {
            "name": c["name"],
            "description": c.get("description", ""),
            "plural_name": c.get("plural_name", c["name"] + "s"),
        }
        for c in ctx.concepts
        if not c["name"].startswith("_")
    ]
    menu = ctx.presentation_config.get("menu", [])
    app_name = ctx.business_schema.get("name", "App")

    data = {
        "appName": app_name,
        "concepts": concepts,
        "menu": menu,
    }
    return f"export const model = {json.dumps(data, indent=2, ensure_ascii=False)};\n"
