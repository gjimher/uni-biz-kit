import json
from pathlib import Path

from ..context import Context


def generate(ctx: Context) -> str:
    config = {}
    for concept in ctx.concepts:
        if concept.get("actions"):
            config[concept["name"]] = [{
                "label": action["label"],
                "function": Path(action["source"]).stem.lstrip("_"),
                "placement": action["placement"],
            } for action in concept["actions"]]
    return "export const BACKEND_ACTIONS = " + json.dumps(config, indent=2) + ";\n"
