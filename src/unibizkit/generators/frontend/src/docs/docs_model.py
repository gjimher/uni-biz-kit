import json
from typing import Any, Dict, List

from ...context import Context

# The documentation pages describe the *enriched* model (the _extended files the
# generators consume), so they also cover what the model never wrote by hand:
# injected concepts (_version, _integration, _design, the task pages...) and the
# permissions the generator adds for them.


def _menu_labels(items: List[Dict[str, Any]], trail: tuple = ()) -> Dict[str, str]:
    """concept name -> its path in the model's menu ('Sales / Orders')."""
    labels = {}
    for item in items:
        if "children" in item:
            labels.update(_menu_labels(item["children"], trail + (item["label"],)))
        elif "concept" in item:
            labels[item["concept"]] = " / ".join(trail + (item["label"],))
    return labels


def _constraints(field: Dict[str, Any]) -> List[str]:
    """Value limits, phrased the way the model wrote them."""
    parts = []
    for key, template in (
        ("min_length", "min length {}"),
        ("max_length", "max length {}"),
        ("min", "min {}"),
        ("max", "max {}"),
    ):
        if key in field:
            parts.append(template.format(field[key]))
    if "precision" in field:
        # scale is optional on the model side (defaults to 0 digits after the point)
        parts.append(f"decimal({field['precision']}, {field.get('scale', 0)})")
    if "on_delete" in field:
        parts.append(f"on delete: {field['on_delete']}")
    if "calculated" in field:
        parts.append("calculated")
    return parts


def _fields(concept: Dict[str, Any]) -> List[Dict[str, Any]]:
    # '_'-prefixed columns are internal plumbing (ownership, profile links,
    # deletion snapshots): they are not part of what the model describes. The
    # virtual '_documents' below is the exception — it is the only place the
    # permissions on a concept's attachments show.
    fields = [
        {
            "name": field["name"],
            "type": field["type"],
            "subtype": field.get("subtype"),
            "target": field.get("target"),
            "required": field["required"],
            "unique": field["unique"],
            "default": field.get("default"),
            "enumValues": field.get("enum_values"),
            "visibility": field["_fe_visibility"],
            "constraints": _constraints(field),
            "description": field["description"],
        }
        for field in concept["fields"]
        if not field["name"].startswith("_")
    ]
    if concept["documents"]["enabled"]:
        # Not a column: the virtual field the ACL uses to govern the concept's
        # document table, listed here so its permissions have a place to show.
        fields.append({
            "name": "_documents",
            "type": "documents",
            "subtype": None,
            "target": None,
            "required": False,
            "unique": False,
            "default": None,
            "enumValues": concept["documents"]["tags"] or None,
            "visibility": "editable",
            "constraints": ["versioned"] if concept["documents"]["versioned"] else [],
            "description": "Files attached to the record (document table).",
        })
    return fields


def _config(ctx: Context) -> Dict[str, Any]:
    menu_labels = _menu_labels(ctx.presentation_config.get("menu") or [])
    concept_workflow = ctx.workflow_config["_concept_workflow"]
    acl = ctx.security_config["_acl"]

    concepts = [
        {
            "name": concept["name"],
            "pluralName": concept["plural_name"],
            "description": concept["description"],
            "archetype": concept["_type"],
            "storage": concept["_be_storage"],
            "generated": concept["name"].startswith("_"),
            "versioned": concept["versioned"],
            "workflow": concept_workflow[concept["name"]]["name"] if concept["name"] in concept_workflow else None,
            "menuLabel": menu_labels.get(concept["name"]),
            "fields": _fields(concept),
        }
        for concept in ctx.concepts
    ]

    workflows = [
        {
            "name": rule["name"],
            "description": rule["description"],
            "concepts": rule["concepts"],
            "states": [
                {
                    "name": state["name"],
                    "description": state["description"],
                    "owners": state["owners"],
                    "assigners": state["assigners"],
                    "retainTaskOwner": state["retain_task_owner"],
                }
                for state in rule["states"]
            ],
        }
        for rule in ctx.workflow_config["workflow_rules"]
    ]

    roles = [
        {
            "name": role["name"],
            "description": role.get("description", ""),
            "profileConcept": role.get("profile_concept"),
        }
        for role in ctx.security_config["roles"]
    ]
    # _anon is not a declared role: it is the built-in one for visitors without a
    # session, and it only exists in the docs when some rule grants it something.
    if any("_anon" in concept_acl["_main"] for concept_acl in acl.values()):
        roles.append({
            "name": "_anon",
            "description": "Built-in role for visitors without a session (anonymous access).",
            "profileConcept": None,
        })

    return {
        "appName": ctx.business_schema["name"],
        # Optional in the model: concepts.jsonc requires only version/name/concepts.
        "appDescription": ctx.business_schema.get("description", ""),
        "roles": roles,
        "concepts": concepts,
        "workflows": workflows,
        "acl": {
            name: {"main": concept_acl["_main"], "fields": concept_acl["_fields"]}
            for name, concept_acl in acl.items()
        },
    }


def generate(ctx: Context) -> str:
    return f"export const docsModel = {json.dumps(_config(ctx), indent=2, ensure_ascii=False)};\n"
