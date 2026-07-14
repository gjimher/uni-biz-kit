import json
from ..context import Context


def _field_editor(field: dict) -> str:
    """Cell editor for the quick-edit table. 'readonly' cells are displayed
    formatted but never sent to the server."""
    if field["_fe_visibility"] == "read_only" or field.get("_prefill_group") or field["name"] == "state":
        return "readonly"
    if field.get("_validation_csv_filename") and field["type"] == "string":
        return "validation"
    if field["type"] == "relation_to_one":
        return "reference"
    if field["type"] == "enum":
        return "select"
    if field["type"] == "boolean":
        return "checkbox"
    if field["type"] in ("integer", "decimal"):
        return "number"
    if field["type"] in ("date", "datetime"):
        return field["type"]
    if field["type"] == "string" and field["size"] == "l":
        return "multiline"
    return "text"


def generate(ctx: Context) -> str:
    config = {}
    for concept in ctx.concepts:
        name = concept["name"]
        workflow = ctx.workflow_config["_concept_workflow"].get(name)

        fields = []
        list_column_names = ["id_presentation"]
        for field in concept["fields"]:
            field_name = field["name"]
            visibility = field["_fe_visibility"]
            # Same pool as the list columns: non-internal fields plus the
            # workflow state (shown read-only), minus non-column types.
            if visibility == "internal" and not (field_name == "state" and workflow):
                continue
            if field["type"] == "relation_to_many":
                continue
            if field.get("_prefill_is_pres_field"):
                continue
            list_column_names.append(field_name)
            if field["type"] == "markdown":
                continue

            editor = _field_editor(field)
            entry = {
                'name': field_name,
                'type': field["type"],
                'editor': editor,
                'required': field["_be_not_null"],
                # NOT NULL without a DB default: a new row cannot be saved
                # unless the cell is filled in.
                'requiredForCreate': (
                    field["_be_not_null"]
                    and field.get("default") is None
                    and "calculated" not in field
                    and editor != "readonly"
                ),
            }
            if field["type"] == "enum":
                entry['values'] = field["enum_values"]
            if field["type"] == "datetime":
                entry['precision'] = field.get("precision", "minute")
            if field["type"] == "relation_to_one":
                entry['target'] = field["target"]
                entry['targetSize'] = ctx.concept_map[field["target"]]["data_size"]
            if field["type"] == "decimal" and field.get("subtype") == "money":
                entry['money'] = {
                    'currency': ctx.presentation_config["currency"],
                    'locale': ctx.presentation_config["number_locale"],
                }
            fields.append(entry)

        default_columns = ctx.presentation_config.get("_list_fields", {}).get(name, list_column_names)

        # A new row can only be created inline when every NOT NULL field without
        # a DB default is fillable in the table (e.g. prefill fields are not).
        editable_names = {f['name'] for f in fields if f['editor'] != "readonly"}
        can_create = all(
            field["name"] in editable_names
            for field in concept["fields"]
            if field["_be_not_null"] and field.get("default") is None and "calculated" not in field
        )

        config[name] = {
            'defaultColumns': default_columns,
            'canCreate': can_create,
            'workflow': workflow,
            'fields': fields,
        }

    config_json = json.dumps(config, indent=2)

    return f"""// Inline quick-edit configuration, one entry per concept.
// defaultColumns: list columns shown when the user has no saved column preference.
// workflow: the concept's workflow (states/owners) or null; rows whose state is
//   not owned by the user's roles are read-only.
// fields: one entry per editable-table column with its cell editor and metadata
//   (editor 'readonly' cells are displayed but never written).
export const QUICK_EDIT_CONFIG = {config_json};
"""
