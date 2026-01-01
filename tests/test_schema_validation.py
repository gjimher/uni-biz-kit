"""
Test Schema Validation

Tests for schema loading and validation functionality.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from src.unibizkit.schema_loader import SchemaLoader, SchemaValidationError

class TestSchemaValidation:
    """Test cases for schema validation."""
    
    def test_valid_schema_validation(self):
        """Test that a valid schema passes validation."""
        schema_loader = SchemaLoader()
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "TestConcept",
                    "fields": [
                        {
                            "name": "testField",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            # Should not raise an exception
            result = schema_loader.load_and_validate(temp_path)
            assert result == valid_schema
        finally:
            os.unlink(temp_path)
    
    def test_invalid_schema_missing_required_fields(self):
        """Test that schema missing required fields fails validation."""
        schema_loader = SchemaLoader()
        invalid_schema = {
            "name": "Test App",  # Missing version
            "concepts": []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_schema, f)
            temp_path = f.name
        
        try:
            with pytest.raises(SchemaValidationError):
                schema_loader.load_and_validate(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_invalid_field_type(self):
        """Test that invalid field types fail validation."""
        schema_loader = SchemaLoader()
        invalid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "TestConcept",
                    "fields": [
                        {
                            "name": "testField",
                            "type": "invalid_type"  # Invalid type
                        }
                    ]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_schema, f)
            temp_path = f.name
        
        try:
            with pytest.raises(SchemaValidationError):
                schema_loader.load_and_validate(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_invalid_json_format(self):
        """Test that invalid JSON format fails validation."""
        schema_loader = SchemaLoader()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json ")  # Invalid JSON
            temp_path = f.name
        
        try:
            with pytest.raises(SchemaValidationError):
                schema_loader.load_and_validate(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_get_concept_by_name(self):
        """Test getting a concept by name."""
        schema_loader = SchemaLoader()
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "Product",
                    "fields": [{"name": "name", "type": "string"}]
                },
                {
                    "name": "Category",
                    "fields": [{"name": "title", "type": "string"}]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            schema_loader.load_and_validate(temp_path)
            
            # Test getting existing concept
            product = schema_loader.get_concept_by_name("Product")
            assert product["name"] == "Product"
            
            # Test getting non-existent concept
            with pytest.raises(KeyError):
                schema_loader.get_concept_by_name("NonExistent")
                
        finally:
            os.unlink(temp_path)
    
    def test_get_all_concepts(self):
        """Test getting all concepts."""
        schema_loader = SchemaLoader()
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {"name": "Product", "fields": [{"name": "name", "type": "string"}]},
                {"name": "Category", "fields": [{"name": "title", "type": "string"}]}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            schema_loader.load_and_validate(temp_path)
            concepts = schema_loader.get_all_concepts()
            assert len(concepts) == 2
            assert concepts[0]["name"] == "Product"
            assert concepts[1]["name"] == "Category"
        finally:
            os.unlink(temp_path)

class TestEcommerceSchema:
    """Test the ecommerce example schema."""
    
    def test_ecommerce_schema_validation(self):
        """Test that the ecommerce schema is valid."""
        schema_loader = SchemaLoader()
        ecommerce_path = Path(__file__).parent.parent / "examples" / "ecommerce_schema.json"
        
        # Should not raise an exception
        result = schema_loader.load_and_validate(str(ecommerce_path))
        
        # Verify basic structure
        assert result["name"] == "ECommerce Platform"
        assert result["version"] == "1.0.0"
        assert len(result["concepts"]) == 5
        
        # Verify concepts
        concept_names = [concept["name"] for concept in result["concepts"]]
        expected_concepts = ["Product", "Category", "Customer", "Order", "OrderItem"]
        assert concept_names == expected_concepts
    
    def test_ecommerce_schema_concepts(self):
        """Test specific concepts in the ecommerce schema."""
        schema_loader = SchemaLoader()
        ecommerce_path = Path(__file__).parent.parent / "examples" / "ecommerce_schema.json"
        schema_loader.load_and_validate(str(ecommerce_path))
        
        # Test Product concept
        product = schema_loader.get_concept_by_name("Product")
        assert product["pluralName"] == "Products"
        assert len(product["fields"]) == 9
        
        # Test that Product has required fields
        required_fields = [field for field in product["fields"] if field.get("required", False)]
        assert len(required_fields) == 5
        
        # Test that Product has unique fields
        unique_fields = [field for field in product["fields"] if field.get("unique", False)]
        assert len(unique_fields) == 1
        assert unique_fields[0]["name"] == "sku"
        
        # Test Category concept
        category = schema_loader.get_concept_by_name("Category")
        assert category["pluralName"] == "Categories"
        assert len(category["fields"]) == 4
        
        # Test relationships
        assert "relationships" in category
        assert len(category["relationships"]) == 1
        assert category["relationships"][0]["type"] == "many-to-many"
        assert category["relationships"][0]["target"] == "Product"