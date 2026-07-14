"""
Schema Loading and Validation Module

Handles loading and validating business concept schemas against the JSON schema definition.
"""

import json
import jsonschema
import csv
from jsoncomment import JsonComment
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

_jsonc = JsonComment()

def _load_jsonc_file(path) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return _jsonc.load(f)

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
        self.deployment_config = None
        self.seed_data_config = None
        self.rules_config = None
        self.deployed_data_config = None
        self.integrations_config = None
        self.validations_config = {"validations": []}
        self.validation_schema = self._load_validation_schema("concepts_schema.json")
        self.presentation_validation_schema = self._load_validation_schema("presentation_schema.json")
        self.security_validation_schema = self._load_validation_schema("security_schema.json")
        self.workflow_validation_schema = self._load_validation_schema("workflow_schema.json")
        self.system_validation_schema = self._load_validation_schema("system_schema.json")
        self.deployment_validation_schema = self._load_validation_schema("deployment_schema.json")
        self.seed_data_validation_schema = self._load_validation_schema("seed_data_schema.json")
        self.rules_validation_schema = self._load_validation_schema("rules_schema.json")
        self.integrations_validation_schema = self._load_validation_schema("integrations_schema.json")
        self.deployed_data_validation_schema = self._load_validation_schema("deployed_data_schema.json")
    
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
            business_schema = _load_jsonc_file(path)

            parent = Path(path).parent

            presentation_path = parent / "presentation.jsonc"
            if not presentation_path.exists():
                raise FileNotFoundError(f"'presentation.jsonc' is mandatory. Please provide it in {parent} (it can be an empty object '{{}}' if you want defaults).")
            self.load_presentation(str(presentation_path))

            security_path = parent / "security.jsonc"
            if not security_path.exists():
                raise FileNotFoundError(f"'security.jsonc' is mandatory. Please provide it in {parent} (it can be an empty object '{{}}' if you want defaults).")
            self.load_security(str(security_path))

            workflow_path = parent / "workflow.jsonc"
            if not workflow_path.exists():
                self.workflow_config = {"workflow_rules": []}
            else:
                self.load_workflow(str(workflow_path))

            system_path = parent / "system.jsonc"
            if system_path.exists():
                self.load_system(str(system_path))
            else:
                self.system_config = {}
                DefaultValidatingDraft7Validator(self.system_validation_schema).validate(self.system_config)

            deployment_path = parent / "deployment.jsonc"
            if deployment_path.exists():
                self.load_deployment(str(deployment_path))
            else:
                self.deployment_config = {}
                DefaultValidatingDraft7Validator(self.deployment_validation_schema).validate(self.deployment_config)

            seed_data_path = parent / "seed_data.jsonc"
            if seed_data_path.exists():
                self.load_seed_data(str(seed_data_path))
            else:
                self.seed_data_config = {"include_test_data": True, "records": {}}

            rules_path = parent / "rules.jsonc"
            if rules_path.exists():
                self.load_rules(str(rules_path))
            else:
                self.rules_config = {"rules": []}

            integrations_path = parent / "integrations.jsonc"
            if integrations_path.exists():
                self.load_integration(str(integrations_path), parent)
            else:
                self.integrations_config = {"roles": ["admin"], "integrations": []}

            deployed_data_path = parent / "deployed_data.jsonc"
            if deployed_data_path.exists():
                config = _load_jsonc_file(deployed_data_path)
                DefaultValidatingDraft7Validator(self.deployed_data_validation_schema).validate(config)
                self.deployed_data_config = config
            else:
                self.deployed_data_config = {"concepts": []}

            # Apply special defaults before main validation/default injection
            self._apply_special_defaults(business_schema)
            
            # Validate against the schema and inject defaults
            # This will now also apply defaults (like separator and show in id_presentation) 
            # to the injected authentication concepts.
            DefaultValidatingDraft7Validator(self.validation_schema).validate(business_schema)

            concept_map = {concept["name"]: concept for concept in business_schema["concepts"]}
            concept_names = set(concept_map)
            for integration in self.integrations_config["integrations"]:
                if integration["target_concept"] not in concept_names:
                    raise SchemaValidationError(
                        f"Integration '{integration['name']}' references unknown target concept "
                        f"'{integration['target_concept']}'"
                    )
                on_removed = integration["on_removed"]
                if isinstance(on_removed, dict):
                    field_name = on_removed["set_false"]
                    target = concept_map[integration["target_concept"]]
                    field = next((item for item in target["fields"] if item["name"] == field_name), None)
                    if field is None:
                        raise SchemaValidationError(
                            f"Integration '{integration['name']}' on_removed references unknown field "
                            f"'{integration['target_concept']}.{field_name}'"
                        )
                    if field["type"] != "boolean":
                        raise SchemaValidationError(
                            f"Integration '{integration['name']}' on_removed set_false field "
                            f"'{integration['target_concept']}.{field_name}' must be boolean"
                        )

            self._validate_reserved_field_names(business_schema)
            self._validate_backend_action_sources(business_schema, parent)
            self._validate_seed_data_against_business_schema(business_schema)
            self._inject_internal_concepts(business_schema)
            self._prepare_deployed_data(business_schema)
            self.load_validations(Path(path).parent, business_schema)
            
            logger.info(f"Successfully loaded and validated schema: {path}")
            self.business_schema = business_schema

            return business_schema
            
        except jsonschema.ValidationError as e:
            error_msg = f"Schema validation failed: {e.message}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Invalid JSON/JSONC format: {e}"
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
        presentation_config = _load_jsonc_file(presentation_path)
        
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
        security_config = _load_jsonc_file(security_path)
        
        # Validate and inject defaults
        DefaultValidatingDraft7Validator(self.security_validation_schema).validate(security_config)
        self._validate_reserved_role_names(security_config)

        self.security_config = security_config
        logger.info(f"Successfully loaded and validated security settings: {security_path}")

    def load_workflow(self, workflow_path: str):
        """
        Load and validate the workflow settings.
        """
        workflow_config = _load_jsonc_file(workflow_path)

        # Validate and inject defaults
        DefaultValidatingDraft7Validator(self.workflow_validation_schema).validate(workflow_config)

        self.workflow_config = workflow_config
        logger.info(f"Successfully loaded and validated workflow settings: {workflow_path}")

    def load_system(self, system_path: str):
        """
        Load and validate the system settings.
        """
        system_config = _load_jsonc_file(system_path)

        # Validate and inject defaults
        DefaultValidatingDraft7Validator(self.system_validation_schema).validate(system_config)

        self.system_config = system_config
        logger.info(f"Successfully loaded and validated system settings: {system_path}")

    def load_deployment(self, deployment_path: str):
        """
        Load and validate the deployment settings.
        """
        deployment_config = _load_jsonc_file(deployment_path)

        DefaultValidatingDraft7Validator(self.deployment_validation_schema).validate(deployment_config)

        # A 'proxy' section marks a proxy-kind model (Caddy landing + reverse proxy),
        # which is handled by a separate generation path and must not carry app sources.
        if "proxy" in deployment_config:
            raise SchemaValidationError(
                f"{deployment_path}: 'proxy' section found next to app sources (concepts.jsonc). "
                "A proxy-kind model contains only deployment.jsonc (with 'proxy'), index.md and assets/."
            )

        self.deployment_config = deployment_config
        logger.info(f"Successfully loaded and validated deployment settings: {deployment_path}")

    def load_seed_data(self, seed_data_path: str):
        """
        Load and validate the optional seed data settings.
        """
        seed_data_config = _load_jsonc_file(seed_data_path)

        DefaultValidatingDraft7Validator(self.seed_data_validation_schema).validate(seed_data_config)

        self.seed_data_config = seed_data_config
        logger.info(f"Successfully loaded and validated seed data settings: {seed_data_path}")

    def load_rules(self, rules_path: str):
        """
        Load and validate the optional FEEL business rules.
        """
        rules_config = _load_jsonc_file(rules_path)

        DefaultValidatingDraft7Validator(self.rules_validation_schema).validate(rules_config)

        self.rules_config = rules_config
        logger.info(f"Successfully loaded and validated rules: {rules_path}")

    def load_integration(self, integrations_path: str, model_dir: Path):
        """Load external replication definitions and validate local source modules."""
        config = _load_jsonc_file(integrations_path)
        DefaultValidatingDraft7Validator(self.integrations_validation_schema).validate(config)
        names = [item["name"] for item in config["integrations"]]
        if len(names) != len(set(names)):
            raise SchemaValidationError("Integration names must be unique")
        configured_roles = self.security_config.get("roles")
        roles = {role["name"] for role in configured_roles} if configured_roles else {"admin", "user"}
        unknown_roles = sorted(set(config["roles"]) - roles)
        if unknown_roles:
            raise SchemaValidationError(f"Integrations reference unknown roles: {unknown_roles}")
        for item in config["integrations"]:
            source_path = model_dir / "backend" / "integrations" / item["source"]
            if not source_path.is_file():
                raise SchemaValidationError(
                    f"Integration '{item['name']}' source does not exist: {item['source']}"
                )
        self.integrations_config = config
        logger.info(f"Successfully loaded and validated integrations: {integrations_path}")

    def load_validations(self, model_dir: Path, business_schema: Dict[str, Any]):
        """
        Load CSV validations from validations/<concept>[-name].csv.
        """
        validations_dir = model_dir / "validations"
        if not validations_dir.exists():
            self.validations_config = {"validations": []}
            return

        concept_map = {concept["name"]: concept for concept in business_schema["concepts"]}
        validations = []
        for csv_path in sorted(validations_dir.glob("*.csv")):
            concept_name = csv_path.stem.split("-", 1)[0]
            if concept_name not in concept_map:
                raise SchemaValidationError(
                    f"Validation file '{csv_path.name}' references unknown concept '{concept_name}'"
                )
            concept = concept_map[concept_name]
            field_map = {field["name"]: field for field in concept["fields"]}

            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                try:
                    columns = [col.strip() for col in next(reader)]
                except StopIteration:
                    raise SchemaValidationError(f"Validation file '{csv_path.name}' is empty")

                if not columns or any(not col for col in columns):
                    raise SchemaValidationError(f"Validation file '{csv_path.name}' has an empty column name")
                if len(set(columns)) != len(columns):
                    raise SchemaValidationError(f"Validation file '{csv_path.name}' has duplicate columns")

                for column in columns:
                    field = field_map.get(column)
                    if not field:
                        raise SchemaValidationError(
                            f"Validation file '{csv_path.name}' references unknown field '{concept_name}.{column}'"
                        )
                    if field["type"] != "string":
                        raise SchemaValidationError(
                            f"Validation file '{csv_path.name}' field '{concept_name}.{column}' must be a string field"
                        )

                rows = []
                for line_number, row in enumerate(reader, start=2):
                    if not row or all(not cell.strip() for cell in row):
                        continue
                    if len(row) != len(columns):
                        raise SchemaValidationError(
                            f"Validation file '{csv_path.name}' line {line_number} has "
                            f"{len(row)} values but expected {len(columns)}"
                        )
                    rows.append([cell.strip() for cell in row])

            validations.append({
                "name": csv_path.stem,
                "concept": concept_name,
                "columns": columns,
                "rows": rows,
            })

        self.validations_config = {"validations": validations}
        logger.info(f"Successfully loaded {len(validations)} CSV validations from: {validations_dir}")
    
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

                if field["type"] == "relation_to_one" and "on_delete" not in field:
                    field["on_delete"] = "cascade" if field.get("required", False) else "set_null"

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
            injected_fields = self._seed_injected_fields(concept_name)
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
                        if field_name in injected_fields:
                            continue
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

    def _seed_injected_fields(self, concept_name: str) -> set:
        """Fields injected later by the SchemaProcessor that seed data may still set:
        'state' on workflow concepts and '_user_pending_link' on profile concepts
        (to pre-link a seeded profile row to a seed user's email)."""
        injected = set()
        for rule in (self.workflow_config or {}).get("workflow_rules", []):
            concepts = [name.strip() for name in rule["concepts"].split(",")]
            if rule["concepts"] == "*" or concept_name in concepts:
                injected.add("state")
        for role in (self.security_config or {}).get("roles", []):
            if role.get("profile_concept") == concept_name:
                injected.add("_user_pending_link")
        return injected

    def _validate_reserved_role_names(self, security_config: Dict[str, Any]):
        for role in security_config.get("roles", []):
            if role["name"].startswith("_"):
                raise SchemaValidationError(
                    f"Role '{role['name']}' uses reserved '_' prefix"
                )

    def _validate_reserved_field_names(self, business_schema: Dict[str, Any]):
        """
        Reserve underscore-prefixed columns for UniBizKit generated internals.
        """
        for concept in business_schema["concepts"]:
            if concept["name"].startswith("_"):
                raise SchemaValidationError(
                    f"Concept name '{concept['name']}' is reserved: user concepts cannot start with '_'"
                )
            for field in concept["fields"]:
                if field["name"].startswith("_"):
                    raise SchemaValidationError(
                        f"Field '{concept['name']}.{field['name']}' uses reserved '_' prefix"
                    )

    def _inject_internal_concepts(self, business_schema: Dict[str, Any]):
        """Add generated operational tables/views before the extended IR is built."""
        def field(name, type_, description, **values):
            return {
                "name": name, "type": type_, "description": description,
                "required": values.pop("required", False),
                "unique": values.pop("unique", False),
                "size": values.pop("size", "s"), **values,
            }

        concepts = business_schema["concepts"]
        security = self.security_config
        level3 = security.setdefault("rules_level_3", [])
        all_roles = [role["name"] for role in security.get("roles") or [{"name": "admin"}, {"name": "user"}]]
        def internal_concept(name, plural, description, presentation_fields, fields, storage):
            return {
                "name": name, "plural_name": plural, "description": description,
                "id_presentation": {"fields": presentation_fields, "separator": " - ", "show": False},
                "fields": fields, "data_size": "s", "checks": [],
                "_be_storage": storage, "_fe_allow_create": False, "_fe_allow_delete": False,
            }

        if self.integrations_config["integrations"]:
            self.presentation_config.setdefault("list_sort", {})["_integration_run"] = "requested_at DESC"
            list_rules = self.presentation_config.setdefault("list_field_rules_level_3", {})
            list_rules.update({
                "_integration": "!*,name,target_concept,schedule,operational_status,last_status,last_completed_at,next_execution_at,last_received_count,last_upserted_count",
                "_integration_run": "!*,integration,trigger,status,requested_by,requested_at,completed_at,received_count,upserted_count,error",
            })
            integration_fields = [
                field("name", "string", "Stable integration name", required=True, unique=True),
                field("description", "string", "Model-defined description", size="m"),
                field("target_concept", "string", "Replicated target concept"),
                field("source_file", "string", "JavaScript source module", size="s"),
                field("schedule", "string", "UTC cron expression"),
                field("on_removed", "json", "Behavior for records explicitly removed at the source", required=True, size="s"),
                field("notes", "string", "Operational notes", size="l"),
                field("operational_status", "enum", "Whether executions are active or paused", required=True, default="active", enum_values=["active", "paused"]),
                field("checkpoint", "json", "Last confirmed source checkpoint", size="s"),
                field("lease_owner", "string", "Current execution lease owner"),
                field("lease_expires_at", "datetime", "Lease expiry", precision="second"),
                field("last_started_at", "datetime", "Last start time", precision="second"),
                field("last_completed_at", "datetime", "Last completion time", precision="second"),
                field("last_status", "string", "Last execution status"),
                field("next_execution_at", "datetime", "Next expected scheduled execution", precision="second"),
                field("last_error", "string", "Last error", size="l"),
                field("last_received_count", "integer", "Records received", required=True, default=0),
                field("last_upserted_count", "integer", "Records upserted", required=True, default=0),
                field("last_removed_count", "integer", "Source removals handled", required=True, default=0),
            ]
            run_fields = [
                field("integration", "relation_to_one", "Integration", required=True, subtype="related_to", target="_integration", on_delete="cascade"),
                field("trigger", "enum", "Invocation source", required=True, enum_values=["manual", "scheduled"]),
                field("requested_by", "string", "Requesting user"),
                field("requested_at", "datetime", "Request time", required=True, precision="second"),
                field("started_at", "datetime", "Start time", precision="second"),
                field("completed_at", "datetime", "Completion time", precision="second"),
                field("status", "enum", "Run status", required=True, enum_values=["queued", "running", "completed", "failed", "skipped"]),
                field("checkpoint_before", "json", "Checkpoint before the run", size="l"),
                field("checkpoint_after", "json", "Checkpoint after the run", size="l"),
                field("pages_count", "integer", "Pages received", required=True, default=0),
                field("received_count", "integer", "Records received", required=True, default=0),
                field("upserted_count", "integer", "Records upserted", required=True, default=0),
                field("removed_count", "integer", "Source removals handled", required=True, default=0),
                field("error", "string", "Execution error", size="l"),
            ]
            integration_concept = internal_concept("_integration", "integrations", "Configured external integrations", ["name"], integration_fields, "table")
            integration_concept["actions"] = [
                {"label": "Run now", "source": "_integration-run.js", "placement": ["edit"]},
                {"label": "Reset checkpoint", "source": "_integration-reset-checkpoint.js", "placement": ["edit"]},
            ]
            concepts.extend([
                integration_concept,
                internal_concept("_integration_run", "integration_runs", "Integration execution history", ["id"], run_fields, "table"),
            ])
            readonly = [f["name"] for f in integration_fields if f["name"] not in ("notes", "operational_status")]
            for role in self.integrations_config["roles"]:
                level3.append({"concept": "_integration", "role": role, "access": "read", "field": "*"})
                level3.append({"concept": "_integration", "role": role, "access": "write", "field": "notes"})
                level3.append({"concept": "_integration", "role": role, "access": "write", "field": "operational_status"})
                level3.extend({"concept": "_integration", "role": role, "access": "read", "field": name} for name in readonly)
                level3.append({"concept": "_integration_run", "role": role, "access": "read", "field": "*"})

        if self.workflow_config.get("workflow_rules") and security["authentication_required"]:
            directory_fields = [
                field("email", "string", "Known user email", required=True, unique=True),
                field("_user", "string", "Authentication user id", unique=True),
                field("roles", "json", "Last known roles", required=True),
                field("source", "string", "Discovery source", required=True),
                field("last_seen_at", "datetime", "Last discovery time"),
            ]
            task_fields = [
                field("concept", "string", "Source concept"), field("record_id", "integer", "Source record id"),
                field("state", "string", "Workflow state"), field("state_task_owner", "string", "Task owner"),
                field("assigners", "json", "Roles allowed to assign"), field("record_text", "string", "Record label", size="m"),
            ]
            concepts.extend([
                internal_concept("_user_directory", "user_directory", "Workflow user discovery cache", ["email"], directory_fields, "table"),
                internal_concept("_workflow_tasks", "workflow_tasks", "Unified workflow task view", ["record_text"], task_fields, "view"),
            ])
            for role in all_roles:
                level3.append({"concept": "_user_directory", "role": role, "access": "read", "field": "*"})
                level3.append({"concept": "_workflow_tasks", "role": role, "access": "read", "field": "*"})

    def _validate_backend_action_sources(self, business_schema: Dict[str, Any], model_dir: Path):
        for concept in business_schema["concepts"]:
            for action in concept["actions"]:
                if Path(action["source"]).name.startswith("_"):
                    raise SchemaValidationError(
                        f"Concept '{concept['name']}' action source uses the reserved internal '_' prefix: {action['source']}"
                    )
                source = model_dir / "backend" / "actions" / action["source"]
                if not source.is_file():
                    raise SchemaValidationError(
                        f"Concept '{concept['name']}' action source does not exist: {action['source']}"
                    )

    def _prepare_deployed_data(self, business_schema: Dict[str, Any]):
        entries = copy.deepcopy(self.deployed_data_config.get("concepts", []))
        names = [entry["concept"] for entry in entries]
        if len(names) != len(set(names)):
            raise SchemaValidationError("deployed_data concept names must be unique")
        if any(name.startswith("_") for name in names):
            raise SchemaValidationError("deployed_data concepts starting with '_' are reserved for generated data")
        if self.integrations_config["integrations"]:
            entries.append({
                "concept": "_integration",
                "on_removed": "delete",
                "records": [{
                    "name": item["name"],
                    "description": item["description"],
                    "target_concept": item["target_concept"],
                    "source_file": item["source"],
                    "schedule": item.get("schedule", ""),
                    "on_removed": item["on_removed"],
                } for item in self.integrations_config["integrations"]],
            })
        concept_map = {concept["name"]: concept for concept in business_schema["concepts"]}
        for entry in entries:
            concept_name = entry["concept"]
            concept_records = entry["records"]
            concept = concept_map.get(concept_name)
            if not concept:
                raise SchemaValidationError(f"deployed_data references unknown concept '{concept_name}'")
            field_map = {field["name"]: field for field in concept["fields"]}
            key_fields = [name for name in concept["id_presentation"]["fields"] if "." not in name]
            if not key_fields or any(name == "id" for name in key_fields):
                raise SchemaValidationError(
                    f"Concept '{concept_name}' needs local, non-id id_presentation fields for deployed_data"
                )
            for name in key_fields:
                field = field_map.get(name)
                if not field or field.get("calculated") or field.get("_be_sql_type") == "SERIAL":
                    raise SchemaValidationError(
                        f"Concept '{concept_name}' has invalid deployed_data key field '{name}'"
                    )
            for record in concept_records:
                missing = [name for name in key_fields if name not in record]
                if missing:
                    raise SchemaValidationError(
                        f"deployed_data record for '{concept_name}' is missing key field(s): {', '.join(missing)}"
                    )
                for name in record:
                    field = field_map.get(name)
                    if not field:
                        raise SchemaValidationError(f"Unknown deployed_data field '{concept_name}.{name}'")
                    if field.get("calculated") or field.get("_be_sql_type") == "SERIAL" or field["type"] == "relation_to_many":
                        raise SchemaValidationError(f"deployed_data cannot set generated field '{concept_name}.{name}'")
        self.deployed_data_config = {"concepts": entries}
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
