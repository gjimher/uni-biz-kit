"""
Schema Loading and Validation Module

Handles loading and validating business concept schemas against the JSON schema definition.
"""

import json
import jsonschema
from jsonschema import Draft7Validator, validators
from pathlib import Path
from typing import Dict, Any, List
import logging
import copy

# Set up logging
logger = logging.getLogger(__name__)

def extend_with_default(validator_class):
    """
    Extends a jsonschema validator to automatically fill in default values.
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, copy.deepcopy(subschema["default"]))

        for error in validate_properties(validator, properties, instance, schema):
            yield error

    return validators.extend(
        validator_class, {"properties": set_defaults},
    )

# Create a validator that injects defaults
DefaultValidatingDraft7Validator = extend_with_default(Draft7Validator)

class SchemaValidationError(Exception):
    """Exception raised when schema validation fails."""
    pass

class SchemaLoader:
    def __init__(self, schema_path: str = None):
        """
        Initialize the schema loader.
        
        Args:
            schema_path: Path to the business schema JSON file
        """
        self.schema_path = schema_path
        self.business_schema = None
        self.validation_schema = self._load_validation_schema()
    
    def _load_validation_schema(self) -> Dict[str, Any]:
        """Load the validation schema from the schemas directory."""
        try:
            schema_file = Path(__file__).parent.parent.parent / "schemas" / "concepts_schema.json"
            with open(schema_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load validation schema: {e}")
            raise
    
    def load_and_validate(self, schema_path: str = None) -> Dict[str, Any]:
        """
        Load and validate a business schema JSON file.
        
        Args:
            schema_path: Path to the business schema JSON file
            
        Returns:
            Parsed and validated business schema
            
        Raises:
            SchemaValidationError: If validation fails
        """
        path = schema_path or self.schema_path
        if not path:
            raise ValueError("No schema path provided")
        
        try:
            # Load the business schema
            with open(path, 'r', encoding='utf-8') as f:
                business_schema = json.load(f)
            
            # Apply special defaults before main validation/default injection
            self._apply_special_defaults(business_schema)
            
            # Validate against the schema and inject defaults
            DefaultValidatingDraft7Validator(self.validation_schema).validate(business_schema)
            
            logger.info(f"Successfully loaded and validated schema: {path}")
            self.business_schema = business_schema
            return business_schema
            
        except jsonschema.ValidationError as e:
            error_msg = f"Schema validation failed: {e.message}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format: {e}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
        except Exception as e:
            error_msg = f"Failed to load schema: {e}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
    
    def _apply_special_defaults(self, data: Dict[str, Any]):
        """
        Apply special conditional defaults that cannot be easily expressed 
        in standard JSON schema.
        """
        if 'concepts' not in data:
            return
            
        for concept in data["concepts"]:
            if 'fields' not in concept:
                continue
                
            for field in concept["fields"]:
                # Rule: required defaults to true for relation_to_one with subtype 'part_of'
                if "required" not in field:
                    if field["type"] == "relation_to_one" and field["subtype"] == "part_of":
                        # Self-reference usually implies nullable root in a hierarchy
                        if field["target"] != concept["name"]:
                            field["required"] = True
    
    def get_concept_by_name(self, name: str) -> Dict[str, Any]:
        """
        Get a concept by its name.
        
        Args:
            name: Name of the concept to find
            
        Returns:
            The concept definition
            
        Raises:
            KeyError: If concept not found
        """
        if not self.business_schema:
            raise ValueError("No business schema loaded")
        
        for concept in self.business_schema["concepts"]:
            if concept["name"] == name:
                return concept
        
        raise KeyError(f"Concept '{name}' not found in schema")
    
    def get_all_concepts(self) -> List[Dict[str, Any]]:
        """
        Get all concepts from the loaded schema.
        
        Returns:
            List of all concept definitions
            
        Raises:
            ValueError: If no schema is loaded
        """
        if not self.business_schema:
            raise ValueError("No business schema loaded")
        
        return self.business_schema["concepts"]