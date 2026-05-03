import pytest
import json
import tempfile
from pathlib import Path
from unibizkit.schema_loader import SchemaLoader, SchemaValidationError

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
        temp_path = Path(temp_dir) / "concepts.json"
        with open(temp_path, 'w') as f:
            json.dump(schema_content, f)
        with open(Path(temp_dir) / "presentation.json", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.json", 'w') as f:
            json.dump({"authentication_required": False}, f)
        
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
        temp_path = Path(temp_dir) / "concepts.json"
        with open(temp_path, 'w') as f:
            json.dump(schema_content, f)
        with open(Path(temp_dir) / "presentation.json", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.json", 'w') as f:
            json.dump({"authentication_required": False}, f)
            
        try:
            loader = SchemaLoader()
            loaded_schema = loader.load_and_validate(str(temp_path))
            
            order_item = loaded_schema['concepts'][0]
            field = order_item['fields'][0]
            
            assert field['name'] == 'order'
            assert 'required' in field, "required should be populated"
            assert field['required'] is True, "required should default to True for part_of relations"

        finally:
            # TemporaryDirectory handles cleanup
            pass


_MINIMAL_CONCEPTS = {
    "version": "1.0.0",
    "name": "Test App",
    "concepts": [{"name": "item", "fields": [{"name": "f1", "type": "string"}], "id_presentation": {"fields": ["f1"]}}],
}


def test_underscore_role_name_raises_error():
    """Role names starting with '_' are reserved and must be rejected at load time."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.json"
        with open(temp_path, 'w') as f:
            json.dump(_MINIMAL_CONCEPTS, f)
        with open(Path(temp_dir) / "presentation.json", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.json", 'w') as f:
            json.dump({"authentication_required": True, "roles": [{"name": "_secret"}]}, f)

        with pytest.raises(SchemaValidationError, match="_secret"):
            SchemaLoader().load_and_validate(str(temp_path))


def test_anon_role_name_raises_error():
    """'_anon' declared explicitly in the roles list must be rejected."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "concepts.json"
        with open(temp_path, 'w') as f:
            json.dump(_MINIMAL_CONCEPTS, f)
        with open(Path(temp_dir) / "presentation.json", 'w') as f:
            json.dump({}, f)
        with open(Path(temp_dir) / "security.json", 'w') as f:
            json.dump({"authentication_required": True, "roles": [{"name": "_anon"}]}, f)

        with pytest.raises(SchemaValidationError, match="_anon"):
            SchemaLoader().load_and_validate(str(temp_path))
