"""
Contract tests for presentation-custom-NN.jsonc overlay loading: naming, ordering,
schema validation and cross-validation against concepts, roles and workflow states.
"""

import json
import pytest
import tempfile
from pathlib import Path
from unibizkit.schema_loader import SchemaLoader, SchemaValidationError


_CONCEPTS = {
    "version": "1.0.0",
    "name": "Test App",
    "concepts": [
        {
            "name": "item",
            "fields": [
                {"name": "f1", "type": "string"},
                {"name": "f2", "type": "string"},
            ],
            "id_presentation": {"fields": ["f1"]},
        }
    ],
}

_WORKFLOW = {
    "workflow_rules": [
        {
            "name": "item_flow",
            "concepts": "item",
            "states": [
                {"name": "draft", "owners": ["user"], "assigners": ["admin"]},
                {"name": "done", "owners": ["user"], "assigners": ["admin"]},
            ],
        }
    ]
}


def _write_model(root: Path, custom_files: dict, workflow: bool = True,
                 presentation: dict = None, authenticated: bool = True):
    (root / "concepts.jsonc").write_text(json.dumps(_CONCEPTS))
    (root / "presentation.jsonc").write_text(json.dumps(presentation or {}))
    (root / "security.jsonc").write_text(json.dumps({"authentication_required": authenticated}))
    (root / "deployment.jsonc").write_text('{"prod_versioning": "dev"}')
    if workflow:
        (root / "workflow.jsonc").write_text(json.dumps(_WORKFLOW))
    for name, content in custom_files.items():
        (root / name).write_text(json.dumps(content))
    return root / "concepts.jsonc"


def _load(custom_files: dict, workflow: bool = True, presentation: dict = None,
          authenticated: bool = True) -> SchemaLoader:
    with tempfile.TemporaryDirectory() as temp_dir:
        loader = SchemaLoader()
        loader.load_and_validate(
            str(_write_model(Path(temp_dir), custom_files, workflow, presentation, authenticated))
        )
        return loader


def test_no_custom_files_yields_empty_overlays():
    loader = _load({})
    assert loader.presentation_custom_config == {"overlays": []}


def test_overlays_load_ordered_with_defaults():
    loader = _load({
        "presentation-custom-10.jsonc": {"roles": ["user"], "lists": {"item": {"columns": ["f1"]}}},
        "presentation-custom-00.jsonc": {"labels": {"fields": {"item.f1": "First"}}},
    })
    overlays = loader.presentation_custom_config["overlays"]
    assert [overlay["file"] for overlay in overlays] == [
        "presentation-custom-00.jsonc", "presentation-custom-10.jsonc",
    ]
    assert overlays[0]["order"] == 0 and overlays[1]["order"] == 10
    # Schema defaults are injected so consumers need no fallbacks
    assert overlays[0]["roles"] == []
    assert overlays[0]["labels"]["titles"] == {}


def test_bad_file_name_is_rejected():
    with pytest.raises(SchemaValidationError, match="presentation-custom-NN"):
        _load({"presentation-custom-1.jsonc": {}})


def test_unknown_section_is_rejected():
    with pytest.raises(SchemaValidationError, match="typo_section"):
        _load({"presentation-custom-00.jsonc": {"typo_section": {}}})


def test_unknown_role_is_rejected():
    with pytest.raises(SchemaValidationError, match="ghost"):
        _load({"presentation-custom-00.jsonc": {"roles": ["ghost"]}})


def test_unknown_concept_is_rejected():
    with pytest.raises(SchemaValidationError, match="nope"):
        _load({"presentation-custom-00.jsonc": {"lists": {"nope": {"columns": ["f1"]}}}})


def test_internal_concepts_are_not_customizable():
    with pytest.raises(SchemaValidationError, match="_workflow_tasks"):
        _load({"presentation-custom-00.jsonc": {"labels": {"titles": {"_workflow_tasks": "Tasks"}}}})


def test_unknown_list_column_is_rejected():
    with pytest.raises(SchemaValidationError, match="item.f9"):
        _load({"presentation-custom-00.jsonc": {"lists": {"item": {"columns": ["f9"]}}}})


def test_generated_list_columns_are_accepted():
    loader = _load({"presentation-custom-00.jsonc": {
        "lists": {"item": {"columns": ["id_presentation", "state", "f1"], "sort": "f1 ASC"}},
    }})
    assert loader.presentation_custom_config["overlays"][0]["lists"]["item"]["sort"] == "f1 ASC"


def test_unknown_form_field_is_rejected():
    with pytest.raises(SchemaValidationError, match="item.f9"):
        _load({"presentation-custom-00.jsonc": {"forms": {"item": {"hide": ["f9"]}}}})


def test_form_sizes_and_moves_load():
    loader = _load({"presentation-custom-00.jsonc": {"forms": {"item": {
        "sizes": {"f1": "1/2"},
        # Move targets may name composite blocks that only exist after
        # enrichment, so they are resolved (and skipped) at runtime.
        "move": [{"field": "some_block", "position": 0}],
    }}}})
    form = loader.presentation_custom_config["overlays"][0]["forms"]["item"]
    assert form["sizes"] == {"f1": "1/2"} and form["move"][0]["field"] == "some_block"


def test_unknown_form_size_field_is_rejected():
    with pytest.raises(SchemaValidationError, match="item.f9"):
        _load({"presentation-custom-00.jsonc": {"forms": {"item": {"sizes": {"f9": "1/2"}}}}})


def test_invalid_form_size_value_is_rejected():
    with pytest.raises(SchemaValidationError):
        _load({"presentation-custom-00.jsonc": {"forms": {"item": {"sizes": {"f1": "17px"}}}}})


def test_unknown_label_field_is_rejected():
    with pytest.raises(SchemaValidationError, match="item.f9"):
        _load({"presentation-custom-00.jsonc": {"labels": {"fields": {"item.f9": "Nine"}}}})


def test_menu_patch_ops_load():
    loader = _load({"presentation-custom-00.jsonc": {"menu": [
        {"op": "rename", "target": "item", "label": "Items"},
        {"op": "move", "target": "item", "position": 0},
        {"op": "remove", "target": "Old group"},
        {"op": "add", "into": "Sales", "item": {"label": "Items", "concept": "item"}},
    ]}})
    assert len(loader.presentation_custom_config["overlays"][0]["menu"]) == 4


def test_unknown_menu_op_is_rejected():
    with pytest.raises(SchemaValidationError):
        _load({"presentation-custom-00.jsonc": {
            "menu": [{"op": "replace", "target": "item"}],
        }})


def test_menu_rename_requires_label():
    with pytest.raises(SchemaValidationError):
        _load({"presentation-custom-00.jsonc": {
            "menu": [{"op": "rename", "target": "item"}],
        }})


def test_unknown_menu_add_concept_is_rejected():
    with pytest.raises(SchemaValidationError, match="nope"):
        _load({"presentation-custom-00.jsonc": {
            "menu": [{"op": "add", "item": {"label": "Top", "children": [{"label": "Bad", "concept": "nope"}]}}],
        }})


def test_unknown_workflow_state_is_rejected():
    with pytest.raises(SchemaValidationError, match="item.archived"):
        _load({"presentation-custom-00.jsonc": {"workflow_states": {"item": {"hide": ["archived"]}}}})


def test_workflow_states_require_a_workflow():
    with pytest.raises(SchemaValidationError, match="no workflow"):
        _load(
            {"presentation-custom-00.jsonc": {"workflow_states": {"item": {"hide": ["draft"]}}}},
            workflow=False,
        )


# --- designer setting (off | dev | production) --------------------------------

def test_designer_production_injects_design_concept():
    loader = _load({}, presentation={"designer": "production", "designer_admin_role": "admin"})
    design = next(c for c in loader.business_schema["concepts"] if c["name"] == "_design")
    # One personalization per user: the owner column must be unique so the
    # client can upsert on it.
    owner = next(f for f in design["fields"] if f["name"] == "_security_owner_id")
    assert owner["unique"] is True
    rules = {r["role"]: r["access"] for r in loader.security_config["rules_level_2"]
             if r["concept"] == "_design"}
    assert rules == {"admin": "write", "user": "owner_write"}


def test_designer_dev_injects_nothing():
    loader = _load({})
    assert not any(c["name"] == "_design" for c in loader.business_schema["concepts"])


def test_designer_off_rejects_overlay_files():
    # 'off' removes the whole customization system from the generated app, so
    # overlay files would silently do nothing: reject them instead.
    with pytest.raises(SchemaValidationError, match="presentation-custom-00"):
        _load(
            {"presentation-custom-00.jsonc": {"labels": {"titles": {"item": "Items"}}}},
            presentation={"designer": "off"},
        )


def test_designer_off_without_overlays_loads():
    loader = _load({}, presentation={"designer": "off"})
    assert loader.presentation_custom_config == {"overlays": []}


def test_designer_production_requires_authentication():
    with pytest.raises(SchemaValidationError, match="authentication_required"):
        _load({}, presentation={"designer": "production"}, authenticated=False)


def test_designer_admin_role_requires_production():
    with pytest.raises(SchemaValidationError, match="designer_admin_role"):
        _load({}, presentation={"designer_admin_role": "admin"})


def test_designer_admin_role_must_exist():
    with pytest.raises(SchemaValidationError, match="ghost"):
        _load({}, presentation={"designer": "production", "designer_admin_role": "ghost"})
