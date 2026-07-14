import pytest
import json
import tempfile
from pathlib import Path
from unibizkit.schema_loader import SchemaLoader, SchemaValidationError


def _write_deployment(path):
    (Path(path) / "deployment.jsonc").write_text('{"prod_versioning":"dev"}')

def test_defaults_population():
    """
    Test that default values from the JSON schema are correctly populated
    into the loaded business schema.
    """
    schema_content = {
        "version": "1.0.0",
        "name": "Test App",
        "concepts": [
            {
                "name": "product",
                "fields": [
                    {
                        "name": "name",
                        "type": "string"
                    }
                ],
                "id_presentation": {
                    "fields": ["name"]
                }
            }
        ]
    }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.jsonc"
        with open(temp_path, 'w') as f:
            json.dump(schema_content, f)
        with open(Path(temp_dir) / "presentation.jsonc", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.jsonc", 'w') as f:
            json.dump({"authentication_required": False}, f)
        _write_deployment(temp_dir)
        
        try:
            loader = SchemaLoader()
            loaded_schema = loader.load_and_validate(str(temp_path))
            
            # Check if data_size was populated (default is 's')
            product_concept = loaded_schema['concepts'][0]
            
            assert 'data_size' in product_concept, "data_size should be populated with default 's'"
            assert product_concept['data_size'] == 's'
            
            # Check nested id_presentation defaults
            assert 'separator' in product_concept['id_presentation'], "separator should be populated with default ' '"
            assert product_concept['id_presentation']['separator'] == ' '
            
            assert 'show' in product_concept['id_presentation'], "show should be populated with default False"
            assert product_concept['id_presentation']['show'] is False
            
            # Check field defaults
            field = product_concept['fields'][0]
            assert 'required' in field, "required should be populated with default False"
            assert field['required'] is False
            assert 'unique' in field, "unique should be populated with default False"
            assert field['unique'] is False

        finally:
            # TemporaryDirectory handles cleanup
            pass

def test_special_required_default():
    """
    Test that 'required' defaults to True for relation_to_one with subtype 'part_of'.
    """
    schema_content = {
        "version": "1.0.0",
        "name": "Test App",
        "concepts": [
            {
                "name": "order_item",
                "fields": [
                    {
                        "name": "order",
                        "type": "relation_to_one",
                        "subtype": "part_of",
                        "target": "order"
                    }
                ],
                "id_presentation": {
                    "fields": ["order"]
                }
            }
        ]
    }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.jsonc"
        with open(temp_path, 'w') as f:
            json.dump(schema_content, f)
        with open(Path(temp_dir) / "presentation.jsonc", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.jsonc", 'w') as f:
            json.dump({"authentication_required": False}, f)
        _write_deployment(temp_dir)
            
        try:
            loader = SchemaLoader()
            loaded_schema = loader.load_and_validate(str(temp_path))
            
            order_item = loaded_schema['concepts'][0]
            field = order_item['fields'][0]
            
            assert field['name'] == 'order'
            assert 'required' in field, "required should be populated"
            assert field['required'] is True, "required should default to True for part_of relations"
            assert field['on_delete'] == 'cascade'

        finally:
            # TemporaryDirectory handles cleanup
            pass


def test_optional_relation_defaults_to_set_null():
    schema_content = {
        "version": "1.0.0",
        "name": "Test App",
        "concepts": [
            {
                "name": "item",
                "fields": [
                    {
                        "name": "category",
                        "type": "relation_to_one",
                        "subtype": "related_to",
                        "target": "category",
                    }
                ],
                "id_presentation": {"fields": ["category"]},
            }
        ],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.jsonc"
        temp_path.write_text(json.dumps(schema_content))
        (Path(temp_dir) / "presentation.jsonc").write_text("{}")
        (Path(temp_dir) / "security.jsonc").write_text(
            json.dumps({"authentication_required": False})
        )
        _write_deployment(temp_dir)

        loaded_schema = SchemaLoader().load_and_validate(str(temp_path))
        relation = loaded_schema["concepts"][0]["fields"][0]
        assert relation["required"] is False
        assert relation["on_delete"] == "set_null"


_MINIMAL_CONCEPTS = {
    "version": "1.0.0",
    "name": "Test App",
    "concepts": [{"name": "item", "fields": [{"name": "f1", "type": "string"}], "id_presentation": {"fields": ["f1"]}}],
}


def test_underscore_role_name_raises_error():
    """Role names starting with '_' are reserved and must be rejected at load time."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.jsonc"
        with open(temp_path, 'w') as f:
            json.dump(_MINIMAL_CONCEPTS, f)
        with open(Path(temp_dir) / "presentation.jsonc", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.jsonc", 'w') as f:
            json.dump({"authentication_required": True, "roles": [{"name": "_secret"}]}, f)
        _write_deployment(temp_dir)

        with pytest.raises(SchemaValidationError, match="_secret"):
            SchemaLoader().load_and_validate(str(temp_path))


def test_anon_role_name_raises_error():
    """'_anon' declared explicitly in the roles list must be rejected."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.jsonc"
        with open(temp_path, 'w') as f:
            json.dump(_MINIMAL_CONCEPTS, f)
        with open(Path(temp_dir) / "presentation.jsonc", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.jsonc", 'w') as f:
            json.dump({"authentication_required": True, "roles": [{"name": "_anon"}]}, f)
        _write_deployment(temp_dir)

        with pytest.raises(SchemaValidationError, match="_anon"):
            SchemaLoader().load_and_validate(str(temp_path))


def test_deployed_data_uses_id_presentation_and_preserves_declared_fields():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "concepts.jsonc").write_text(json.dumps(_MINIMAL_CONCEPTS))
        (root / "presentation.jsonc").write_text("{}")
        (root / "security.jsonc").write_text('{"authentication_required":false}')
        (root / "deployed_data.jsonc").write_text(json.dumps({
            "concepts": [{"concept": "item", "records": [{"f1": "stable-key"}]}]
        }))
        _write_deployment(root)

        loader = SchemaLoader()
        loader.load_and_validate(str(root / "concepts.jsonc"))
        assert loader.deployed_data_config == {"concepts": [{
            "concept": "item", "on_removed": "ignore", "records": [{"f1": "stable-key"}]
        }]}


def test_deployed_data_rejects_generated_id_as_key():
    schema = json.loads(json.dumps(_MINIMAL_CONCEPTS))
    schema["concepts"][0]["id_presentation"]["fields"] = ["id"]
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "concepts.jsonc").write_text(json.dumps(schema))
        (root / "presentation.jsonc").write_text("{}")
        (root / "security.jsonc").write_text('{"authentication_required":false}')
        (root / "deployed_data.jsonc").write_text(json.dumps({
            "concepts": [{"concept": "item", "records": [{"f1": "x"}]}]
        }))
        _write_deployment(root)
        with pytest.raises(SchemaValidationError, match="non-id id_presentation"):
            SchemaLoader().load_and_validate(str(root / "concepts.jsonc"))
