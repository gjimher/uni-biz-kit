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
        self.presentation_config = None
        self.security_config = None
        self.workflow_config = None
        self.system_config = None
        self.seed_data_config = None
        self.validation_schema = self._load_validation_schema("concepts_schema.json")
        self.presentation_validation_schema = self._load_validation_schema("presentation_schema.json")
        self.security_validation_schema = self._load_validation_schema("security_schema.json")
        self.workflow_validation_schema = self._load_validation_schema("workflow_schema.json")
        self.system_validation_schema = self._load_validation_schema("system_schema.json")
        self.seed_data_validation_schema = self._load_validation_schema("seed_data_schema.json")
    
    def _load_validation_schema(self, schema_name: str) -> Dict[str, Any]:
        """Load a validation schema from the schemas directory."""
        try:
            schema_file = Path(__file__).parent.parent.parent / "schemas" / schema_name
            with open(schema_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load validation schema {schema_name}: {e}")
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
            
            # Try to load presentation.json
            presentation_path = Path(path).parent / "presentation.json"
            if not presentation_path.exists():
                raise FileNotFoundError(f"'presentation.json' is mandatory. Please provide it in {presentation_path.parent} (it can be an empty object '{{}}' if you want defaults).")
            
            self.load_presentation(str(presentation_path))

            # Try to load security.json
            security_path = Path(path).parent / "security.json"
            if not security_path.exists():
                raise FileNotFoundError(f"'security.json' is mandatory. Please provide it in {security_path.parent} (it can be an empty object '{{}}' if you want defaults).")
            
            self.load_security(str(security_path))

            # Try to load workflow.json
            workflow_path = Path(path).parent / "workflow.json"
            if not workflow_path.exists():
                # For backward compatibility and when no workflow is needed
                self.workflow_config = {"workflow_rules": []}
            else:
                self.load_workflow(str(workflow_path))

            # Try to load system.json (optional)
            system_path = Path(path).parent / "system.json"
            if system_path.exists():
                self.load_system(str(system_path))
            else:
                # Apply defaults from system schema
                self.system_config = {}
                DefaultValidatingDraft7Validator(self.system_validation_schema).validate(self.system_config)

            # Try to load seed_data.json (optional)
            seed_data_path = Path(path).parent / "seed_data.json"
            if seed_data_path.exists():
                self.load_seed_data(str(seed_data_path))
            else:
                self.seed_data_config = {"include_test_data": True, "records": {}}

            # Apply special defaults before main validation/default injection
            self._apply_special_defaults(business_schema)
            
            # Validate against the schema and inject defaults
            # This will now also apply defaults (like separator and show in id_presentation) 
            # to the injected authentication concepts.
            DefaultValidatingDraft7Validator(self.validation_schema).validate(business_schema)

            self._validate_seed_data_against_business_schema(business_schema)
            
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

    def load_presentation(self, presentation_path: str):
        """
        Load and validate the presentation settings.
        """
        with open(presentation_path, 'r', encoding='utf-8') as f:
            presentation_config = json.load(f)
        
        # Validate and inject defaults
        # We MUST use the custom validator that injects defaults
        validator = extend_with_default(Draft7Validator)(self.presentation_validation_schema)
        validator.validate(presentation_config)
        
        self.presentation_config = presentation_config
        logger.info(f"Successfully loaded and validated presentation settings: {presentation_path}")
    
    def load_security(self, security_path: str):
        """
        Load and validate the security settings.
        """
        with open(security_path, 'r', encoding='utf-8') as f:
            security_config = json.load(f)
        
        # Validate and inject defaults
        DefaultValidatingDraft7Validator(self.security_validation_schema).validate(security_config)
        
        self.security_config = security_config
        logger.info(f"Successfully loaded and validated security settings: {security_path}")

    def load_workflow(self, workflow_path: str):
        """
        Load and validate the workflow settings.
        """
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow_config = json.load(f)

        # Validate and inject defaults
        DefaultValidatingDraft7Validator(self.workflow_validation_schema).validate(workflow_config)

        self.workflow_config = workflow_config
        logger.info(f"Successfully loaded and validated workflow settings: {workflow_path}")

    def load_system(self, system_path: str):
        """
        Load and validate the system settings.
        """
        with open(system_path, 'r', encoding='utf-8') as f:
            system_config = json.load(f)

        # Validate and inject defaults
        DefaultValidatingDraft7Validator(self.system_validation_schema).validate(system_config)

        self.system_config = system_config
        logger.info(f"Successfully loaded and validated system settings: {system_path}")

    def load_seed_data(self, seed_data_path: str):
        """
        Load and validate the optional seed data settings.
        """
        with open(seed_data_path, 'r', encoding='utf-8') as f:
            seed_data_config = json.load(f)

        DefaultValidatingDraft7Validator(self.seed_data_validation_schema).validate(seed_data_config)

        self.seed_data_config = seed_data_config
        logger.info(f"Successfully loaded and validated seed data settings: {seed_data_path}")
    
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

    def _validate_seed_data_against_business_schema(self, business_schema: Dict[str, Any]):
        """
        Validate seed data references against concepts, fields and document tags.
        """
        seed_data = self.seed_data_config or {"include_test_data": True, "records": {}}
        concept_map = {concept["name"]: concept for concept in business_schema["concepts"]}
        seed_ids = {
            concept_name: {
                str(record["id"])
                for record in records
                if "id" in record
            }
            for concept_name, records in seed_data["records"].items()
        }

        for concept_name, records in seed_data["records"].items():
            if concept_name not in concept_map:
                raise SchemaValidationError(f"Seed data references unknown concept '{concept_name}'")

            concept = concept_map[concept_name]
            field_map = {field["name"]: field for field in concept["fields"]}
            seen_ids = set()

            for record in records:
                if "id" in record:
                    seed_id = str(record["id"])
                    if seed_id in seen_ids:
                        raise SchemaValidationError(f"Seed data has duplicate id '{seed_id}' for concept '{concept_name}'")
                    seen_ids.add(seed_id)

                for field_name, value in record.items():
                    if field_name in ("id", "documents"):
                        continue
                    if field_name not in field_map:
                        raise SchemaValidationError(
                            f"Seed data references unknown field '{concept_name}.{field_name}'"
                        )
                    field = field_map[field_name]
                    if field["type"] == "relation_to_many" and value is not None and not isinstance(value, list):
                        raise SchemaValidationError(
                            f"Seed data field '{concept_name}.{field_name}' must be a list of ids"
                        )
                    if field["type"] == "relation_to_one" and value is not None:
                        self._validate_seed_relation_reference(
                            concept_name, field_name, field["target"], value, seed_ids
                        )
                    if field["type"] == "relation_to_many" and value is not None:
                        for target_id in value:
                            self._validate_seed_relation_reference(
                                concept_name, field_name, field["target"], target_id, seed_ids
                            )

                for document in record.get("documents", []):
                    self._validate_seed_document(concept, document)

    def _validate_seed_document(self, concept: Dict[str, Any], document: Dict[str, Any]):
        concept_name = concept["name"]
        docs = concept["documents"]
        if not docs["enabled"]:
            raise SchemaValidationError(f"Seed document concept '{concept_name}' does not have documents enabled")
        if document["tag"] not in docs["tags"]:
            raise SchemaValidationError(
                f"Seed document tag '{document['tag']}' is not allowed for concept '{concept_name}'"
            )

    def _validate_seed_relation_reference(
        self,
        concept_name: str,
        field_name: str,
        target_concept: str,
        target_id: Any,
        seed_ids: Dict[str, Any],
    ):
        if str(target_id) not in seed_ids.get(target_concept, set()):
            raise SchemaValidationError(
                f"Seed data field '{concept_name}.{field_name}' references unknown seed id "
                f"'{target_id}' for concept '{target_concept}'"
            )
    
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
