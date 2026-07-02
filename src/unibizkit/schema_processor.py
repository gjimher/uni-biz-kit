"""
Schema Processor Module

Enriches the raw business schema with internal metadata (_prefixed fields)
to simplify downstream generation (SQL, Frontend).

Naming Convention for Enriched Fields:
- _be_*: Backend-specific metadata (SQL types, constraints, table names).
- _fe_*: Frontend-specific metadata (UI components, grid widths, validations).
- _type: Calculated archetype (root, part_of, recursive_part_of).
"""

import copy
import re
from typing import Dict, Any, List, Optional

class SchemaProcessor:
    @staticmethod
    def evaluate_list_fields(all_names: List[str], filter_str: str) -> List[str]:
        result_names = []
        if not filter_str.strip():
            return result_names
            
        parts = [p.strip() for p in filter_str.split(',') if p.strip()]
        for part in parts:
            pos_match = re.match(r'^([^\[\]]+)\[([^\]]+)\]$', part)
            if pos_match:
                target = pos_match.group(1).strip()
                pos = pos_match.group(2).strip()
                
                if target not in all_names:
                    continue
                    
                if target in result_names:
                    result_names.remove(target)
                    
                if pos == '0':
                    result_names.insert(0, target)
                elif pos == '-1':
                    result_names.append(target)
                else:
                    if pos in result_names:
                        idx = result_names.index(pos)
                        result_names.insert(idx + 1, target)
                    else:
                        result_names.append(target)
                continue

            if part == '*':
                for name in all_names:
                    if name not in result_names:
                        result_names.append(name)
            elif part.startswith('!>='):
                target = part[3:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[idx:]:
                        if name in result_names:
                            result_names.remove(name)
            elif part.startswith('!>'):
                target = part[2:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[idx+1:]:
                        if name in result_names:
                            result_names.remove(name)
            elif part.startswith('!<='):
                target = part[3:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[:idx+1]:
                        if name in result_names:
                            result_names.remove(name)
            elif part.startswith('!<'):
                target = part[2:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[:idx]:
                        if name in result_names:
                            result_names.remove(name)
            elif part.startswith('>='):
                target = part[2:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[idx:]:
                        if name not in result_names:
                            result_names.append(name)
            elif part.startswith('>'):
                target = part[1:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[idx+1:]:
                        if name not in result_names:
                            result_names.append(name)
            elif part.startswith('<='):
                target = part[2:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[:idx+1]:
                        if name not in result_names:
                            result_names.append(name)
            elif part.startswith('<'):
                target = part[1:]
                if target in all_names:
                    idx = all_names.index(target)
                    for name in all_names[:idx]:
                        if name not in result_names:
                            result_names.append(name)
            elif part.startswith('!'):
                target = part[1:]
                if target.endswith('*'):
                    prefix = target[:-1]
                    for name in all_names:
                        if name.startswith(prefix) and name in result_names:
                            result_names.remove(name)
                elif target in result_names:
                    result_names.remove(target)
            else:
                target = part
                if target.endswith('*'):
                    prefix = target[:-1]
                    for name in all_names:
                        if name.startswith(prefix) and name not in result_names:
                            result_names.append(name)
                elif target in all_names:
                    if target in result_names:
                        result_names.remove(target)
                    result_names.append(target)
        return result_names

    def __init__(self, schema: Dict[str, Any], security_config: Optional[Dict[str, Any]] = None, presentation_config: Optional[Dict[str, Any]] = None, workflow_config: Optional[Dict[str, Any]] = None, system_config: Optional[Dict[str, Any]] = None, deployment_config: Optional[Dict[str, Any]] = None, validations_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Schema Processor.

        Args:
            schema: The raw loaded business schema.
            security_config: The loaded security configuration.
            presentation_config: The loaded presentation configuration.
            workflow_config: The loaded workflow configuration.
            system_config: The loaded system configuration (SMTP, base_url).
            deployment_config: The loaded deployment configuration (base_uri).
            validations_config: The loaded CSV-driven validation configuration.
        """
        self.raw_schema = schema
        self.security_config = security_config or {"authentication_required": False}
        self.security_extended = copy.deepcopy(self.security_config)
        self.presentation_extended = copy.deepcopy(presentation_config or {})
        self.workflow_extended = copy.deepcopy(workflow_config or {"workflow_rules": []})
        self.system_extended = copy.deepcopy(system_config or {})
        self.deployment_extended = copy.deepcopy(deployment_config or {})
        self.validations_config = copy.deepcopy(validations_config or {"validations": []})
        self._validations_by_concept = {}
        
        # We work on a deep copy to avoid mutating the original
        self.extended_schema = copy.deepcopy(schema)
        
        self.concepts = self.extended_schema["concepts"]
        self.concept_map = {c["name"]: c for c in self.concepts}

    def process(self) -> Dict[str, Any]:
        """
        Enrich the schema and presentation with internal metadata.

        Returns:
            The extended schema dictionary.
        """
        # 0. Apply documents defaults to all concepts so generators can use [] access.
        # tags is intentionally NOT defaulted here: it is only present when explicitly
        # configured, and generators always check ["enabled"] before accessing ["tags"].
        for concept in self.concepts:
            if "documents" not in concept:
                concept["documents"] = {}
            docs = concept["documents"]
            docs.setdefault("enabled", False)
            docs.setdefault("versioned", False)

        # 0. Enrich Workflow
        self._enrich_workflow()

        # 0. Enrich CSV validations
        self._enrich_validations()

        # Expand prefill fields before security ACL and list field pool computation
        self._expand_prefill_fields()

        # 0. Enrich Security
        self._enrich_security()

        # 0.5 Enrich Presentation
        self._enrich_presentation()
        from .react_admin_generator import ReactAdminGenerator

        l1_rules = self.presentation_extended["list_field_rules_level_1"]
        l2_rules = self.presentation_extended["list_field_rules_level_2"]
        l3_rules = self.presentation_extended["list_field_rules_level_3"]
        
        self.presentation_extended["_list_fields"] = {}
        
        def get_matched_rule(c_name, rules):
            if not rules:
                return None
            if c_name in rules:
                return rules[c_name]
            # Try patterns (e.g. customer*)
            for pattern, rule in rules.items():
                if pattern == "*":
                    continue # Handle * last
                if pattern.endswith("*") and c_name.startswith(pattern[:-1]):
                    return rule
            return rules.get("*")

        for concept in self.concepts:
            c_name = concept["name"]
            # Pool includes id_presentation and all non-internal fields
            pool = ["id_presentation"] + [f["name"] for f in concept["fields"] if f.get("_fe_visibility", "visible") != "internal"]
            
            # Level 1
            rule1 = get_matched_rule(c_name, l1_rules) or "*"
            resolved = ReactAdminGenerator.filter_list_fields(pool, [], rule1)
            
            # Level 2
            rule2 = get_matched_rule(c_name, l2_rules)
            if rule2:
                resolved = ReactAdminGenerator.filter_list_fields(pool, resolved, rule2)
            
            # Level 3
            rule3 = get_matched_rule(c_name, l3_rules)
            if rule3:
                resolved = ReactAdminGenerator.filter_list_fields(pool, resolved, rule3)
            
            self.presentation_extended["_list_fields"][c_name] = resolved

        # Determine which concepts have owner_write
        owner_write_concepts = set()
        _acl = self.security_extended.get("_acl", {})
        for concept_name, concept_acl in _acl.items():
            for role, access in concept_acl.get("_main", {}).items():
                if access == "owner_write":
                    owner_write_concepts.add(concept_name)
            for field_rules in concept_acl.get("_fields", {}).values():
                for role, access in field_rules.items():
                    if access == "owner_write":
                        owner_write_concepts.add(concept_name)

        # 1. Pass 1: Local Concept Processing (Fields, Basic Metadata)
        # We need to iterate by index to modify the list in place with a reordered dict
        for idx, concept in enumerate(self.concepts):
            if concept["name"] in owner_write_concepts:
                if not any(f["name"] == "_security_owner_id" for f in concept["fields"]):
                    concept["fields"].append({
                        "name": "_security_owner_id",
                        "type": "string",
                        "size": "l",
                        "description": "ID of the user who owns this record",
                        "required": False,
                        "unique": False,
                    })

            # Process basics returns a NEW dict with reordered keys
            new_concept = self._process_concept_basics(concept)
            
            # Enrich with presentation logic
            self._process_presentation_logic(new_concept)
            
            # Update the reference in the list
            self.concepts[idx] = new_concept
            
            # Process fields (fields are inside the new_concept now)
            for field in new_concept["fields"]:
                self._process_field(field, new_concept)
        
        # Pass 2: Cross-Concept Processing (Relationships)
        for concept in self.concepts:
            self._process_relationships(concept)

        # Enrich Deployment: normalize base_uri to always end with /
        self._enrich_deployment()

        self._validate_payments()

        return self.extended_schema

    def _validate_payments(self):
        """Check that the payments config points to an existing concept and fields."""
        payments = self.system_extended.get("payments")
        if not payments:
            return
        concept = self.concept_map.get(payments["concept"])
        if concept is None:
            raise ValueError(
                f"payments.concept references unknown concept '{payments['concept']}'"
            )
        field_names = {f["name"] for f in concept["fields"]}
        for key in ("amount_field", "status_field", "reference_field"):
            if payments[key] not in field_names:
                raise ValueError(
                    f"payments.{key} references unknown field "
                    f"'{payments[key]}' in concept '{payments['concept']}'"
                )

    def _enrich_deployment(self):
        base_uri = self.deployment_extended.get("base_uri", "/")
        if not base_uri.endswith("/"):
            base_uri = base_uri + "/"
        self.deployment_extended["base_uri"] = base_uri

    def _enrich_validations(self):
        validations = self.validations_config.get("validations", [])
        self._validations_by_concept = {}
        for validation in validations:
            self._validations_by_concept.setdefault(validation["concept"], []).append(validation)
        for concept in self.concepts:
            concept_validations = self._validations_by_concept.get(concept["name"], [])
            for validation in concept_validations:
                for index, field_name in enumerate(validation["columns"]):
                    field = self.concept_map[concept["name"]]["fields"]
                    for candidate in field:
                        if candidate["name"] == field_name:
                            candidate["_validation_csv_filename"] = f"{validation['name']}.csv"
                            candidate["_validation_csv_column"] = index
                            break

    def _add_validation(self, validation: Dict[str, Any]):
        self._validations_by_concept.setdefault(validation["concept"], []).append(validation)

    @property
    def all_validations_with_rows(self) -> list:
        return [v for vs in self._validations_by_concept.values() for v in vs]

    def _enrich_workflow(self):
        """
        Map workflows to concepts and inject necessary fields.
        """
        # Create a concept-to-workflow map for easy lookup
        concept_to_workflow = {}
        # Support renaming from 'workflows' to 'workflow_rules'
        workflow_rules = self.workflow_extended.get("workflow_rules", self.workflow_extended.get("workflows", []))
        
        # Collect and expand wildcard concept rules
        import fnmatch
        for rule in workflow_rules:
            # Concepts can be comma-separated string
            concepts_str = rule.get("concepts", "")
            if isinstance(concepts_str, list):
                # Backwards compat if needed, but schema changed to string
                concepts_parts = concepts_str
            else:
                concepts_parts = [p.strip() for p in concepts_str.split(',') if p.strip()]
            
            for part in concepts_parts:
                matched_concepts = []
                if part == "*":
                    matched_concepts = [c["name"] for c in self.concepts]
                elif "*" in part:
                    matched_concepts = [c["name"] for c in self.concepts if fnmatch.fnmatch(c["name"], part)]
                else:
                    matched_concepts = [part]
                
                for c_name in matched_concepts:
                    concept_to_workflow[c_name] = rule
        
        # Inject state and state_info fields to concepts with workflows
        self.workflow_extended["_concept_workflow"] = {}
        for concept in self.concepts:
            concept_name = concept["name"]
            if concept_name in concept_to_workflow:
                wf = concept_to_workflow[concept_name]
                self.workflow_extended["_concept_workflow"][concept_name] = wf
                
                # Check for existing state field, if not, add it
                if not any(f["name"] == "state" for f in concept["fields"]):
                    initial_state = wf["states"][0]["name"] if wf["states"] else "initial"
                    concept["fields"].append({
                        "name": "state",
                        "type": "string",
                        "default": initial_state,
                        "description": "Workflow state",
                        "required": True,
                        "unique": False,
                        "size": "s"
                    })

                # Check for state_info field, if not, add it
                if not any(f["name"] == "state_info" for f in concept["fields"]):
                    concept["fields"].append({
                        "name": "state_info",
                        "type": "string", # Will be mapped to XML in _determine_sql_type
                        "description": "Workflow history (XML)",
                        "required": False,
                        "unique": False,
                        "size": "l"
                    })

    def _enrich_presentation(self):
        """Inject default values for presentation settings if missing."""
        if "list_field_rules_level_1" not in self.presentation_extended:
            self.presentation_extended["list_field_rules_level_1"] = {"*": "*,!id_presentation,!_*"}
        
        if "list_field_rules_level_2" not in self.presentation_extended:
            self.presentation_extended["list_field_rules_level_2"] = {}
            
        if "list_field_rules_level_3" not in self.presentation_extended:
            self.presentation_extended["list_field_rules_level_3"] = {}

    def _enrich_security(self):
        """Inject default roles and users if missing, and expand rule wildcards."""
        # Propagate SSO config with defaults
        if "sso" in self.security_extended:
            sso = self.security_extended["sso"]
            sso.setdefault("enabled", False)
            sso.setdefault("role_claim", "roles")
            sso.setdefault("default_role", "user")

        # Ensure basic structures are always present for schema validation
        if "roles" not in self.security_extended or not self.security_extended["roles"]:
            self.security_extended["roles"] = [
                {"name": "admin", "description": "System Administrator"},
                {"name": "user", "description": "Standard User"}
            ]
        
        if "users" not in self.security_extended or not self.security_extended["users"]:
            self.security_extended["users"] = [
                {"email": "admin@test.com", "password": "adminadmin", "roles": ["admin"]},
                {"email": "user@test.com", "password": "useruser", "roles": ["user"]}
            ]

        self._enrich_profile_concepts()

        if not self.security_extended["authentication_required"]:
            # Set default empty _acl even if auth is disabled for schema consistency
            self.security_extended["_acl"] = {}
            # Ensure rules_level fields are also present
            for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
                if level not in self.security_extended:
                    self.security_extended[level] = []
            return

        # Handle defaults for rules_level_1, 2, 3
        if "rules_level_1" not in self.security_extended or not self.security_extended["rules_level_1"]:
            self.security_extended["rules_level_1"] = [
                {"concept": "*", "role": "admin", "access": "write", "field": "*"},
                {"concept": "*", "role": "user", "access": "read", "field": "*"}
            ]
        
        if "rules_level_2" not in self.security_extended:
            self.security_extended["rules_level_2"] = []
        if "rules_level_3" not in self.security_extended:
            self.security_extended["rules_level_3"] = []

        # Validate _anon rules: only concept-level read is allowed
        for level_key in ["rules_level_1", "rules_level_2", "rules_level_3"]:
            for rule in self.security_extended.get(level_key, []):
                if rule["role"] != "_anon":
                    continue
                if rule["access"] != "read":
                    raise ValueError(
                        f"Role '_anon' only supports 'read' access, got '{rule['access']}' "
                        f"for concept '{rule['concept']}' in {level_key}"
                    )
                if rule.get("field", "*") != "*":
                    raise ValueError(
                        f"Role '_anon' only supports concept-level access (field '*'), "
                        f"got field '{rule['field']}' for concept '{rule['concept']}' in {level_key}"
                    )

        # Map: parent concept name -> [child concept names] (via 'part_of' composition).
        # Only 'part_of' relations imply ownership, so only they inherit the parent's
        # access rules. 'related_to' lookups (e.g. order -> shipping_method) must NOT
        # propagate, otherwise a lookup's read rule would clobber the child's own
        # owner_write rule (e.g. order would inherit shipping_method's 'read').
        child_concepts_map: Dict[str, list] = {}
        for concept in self.concepts:
            for field in concept["fields"]:
                if field["type"] == "relation_to_one" and field.get("subtype") == "part_of":
                    parent = field["target"]
                    child_concepts_map.setdefault(parent, []).append(concept["name"])

        def expand_rules(rules):
            import fnmatch
            expanded = []
            for rule in rules:
                field_val = rule.get("field", "*")

                concepts_to_apply = []
                if rule["concept"] == "*":
                    concepts_to_apply = [c["name"] for c in self.concepts]
                else:
                    concepts_to_apply = [rule["concept"]]

                for c_name in concepts_to_apply:
                    if field_val == "*":
                        expanded.append({
                            "role": rule["role"],
                            "concept": c_name,
                            "field": "*",
                            "access": rule["access"]
                        })
                        # Propagate to child concepts (those with a FK back to c_name)
                        for child_name in child_concepts_map.get(c_name, []):
                            expanded.append({
                                "role": rule["role"],
                                "concept": child_name,
                                "field": "*",
                                "access": rule["access"]
                            })
                    elif "*" in field_val:
                        concept = self.concept_map.get(c_name)
                        if concept:
                            for field in concept["fields"]:
                                if fnmatch.fnmatch(field["name"], field_val):
                                    expanded.append({
                                        "role": rule["role"],
                                        "concept": c_name,
                                        "field": field["name"],
                                        "access": rule["access"]
                                    })
                    else:
                        # Check if field_val is the singular name of a child concept
                        child_names = child_concepts_map.get(c_name, [])
                        if field_val in child_names:
                            expanded.append({
                                "role": rule["role"],
                                "concept": field_val,
                                "field": "*",
                                "access": rule["access"]
                            })
                        else:
                            expanded.append({
                                "role": rule["role"],
                                "concept": c_name,
                                "field": field_val,
                                "access": rule["access"]
                            })
            return expanded

        # Merge rules: higher levels override lower levels
        rules_map = {} # (concept, field, role) -> access
        for level_key in ["rules_level_1", "rules_level_2", "rules_level_3"]:
            level_rules = self.security_extended.get(level_key, [])
            for rule in expand_rules(level_rules):
                rules_map[(rule["concept"], rule["field"], rule["role"])] = rule["access"]
        
        # Build _acl structure: concept -> { _main: {role: access}, _fields: {field: {role: access}} }
        _acl = {}
        role_names = [r["name"] for r in self.security_extended["roles"]]
        # _anon is a built-in role (not in the roles list) handled separately
        acl_role_names = role_names + ["_anon"]

        for concept in self.concepts:
            concept_name = concept["name"]
            concept_acl = {"_main": {}, "_fields": {}}

            # 1. Main access (concept-level)
            for role_name in acl_role_names:
                access = rules_map.get((concept_name, "*", role_name))
                if access:
                    concept_acl["_main"][role_name] = access

            # 2. Field-level access (explicit for all fields)
            for field in concept["fields"]:
                field_name = field["name"]
                field_rules = {}

                # Check each role for this field
                for role_name in acl_role_names:
                    # Specific field rule overrides concept rule
                    access = rules_map.get((concept_name, field_name, role_name))
                    if not access:
                        # Fallback to main rule
                        access = concept_acl["_main"].get(role_name)

                    if access:
                        field_rules[role_name] = access

                if field_rules:
                    concept_acl["_fields"][field_name] = field_rules

            # 3. Virtual _documents field (controls access to the concept's document table)
            if concept["documents"]["enabled"]:
                docs_field_rules = {}
                for role_name in acl_role_names:
                    access = rules_map.get((concept_name, "_documents", role_name))
                    if not access:
                        access = concept_acl["_main"].get(role_name)
                    if access:
                        docs_field_rules[role_name] = access
                if docs_field_rules:
                    concept_acl["_fields"]["_documents"] = docs_field_rules

            if concept_acl["_main"] or concept_acl["_fields"]:
                _acl[concept_name] = concept_acl
                
        self.security_extended["_acl"] = _acl

    def _enrich_profile_concepts(self):
        """Resolve roles[].profile_concept and inject generated profile link fields."""
        profile_mappings = []

        for role in self.security_extended["roles"]:
            profile_concept = role.get("profile_concept")
            if not profile_concept:
                continue

            role_name = role["name"]
            concept = self.concept_map.get(profile_concept)
            if concept is None:
                raise ValueError(
                    f"Role '{role_name}' references unknown profile_concept '{profile_concept}'"
                )

            if "_profile_for_roles" not in concept:
                concept["_profile_for_roles"] = []
            concept["_profile_for_roles"].append(role_name)
            self._inject_profile_fields(concept)
            self._validate_profile_autocreate_defaults(concept, role_name)
            profile_mappings.append({"role": role_name, "concept": profile_concept})

        self.security_extended["_profile_concepts"] = profile_mappings

    def _inject_profile_fields(self, concept: Dict[str, Any]):
        existing_field_names = {field["name"] for field in concept["fields"]}

        if "_user" not in existing_field_names:
            concept["fields"].append({
                "name": "_user",
                "type": "string",
                "size": "s",
                "description": "Auth user id linked to this profile",
                "required": False,
                "unique": True,
            })

        if "_user_email" not in existing_field_names:
            concept["fields"].append({
                "name": "_user_email",
                "type": "string",
                "size": "s",
                "description": "Auth user email linked to this profile",
                "required": False,
                "unique": False,
            })

        if "_user_pending_link" not in existing_field_names:
            concept["fields"].append({
                "name": "_user_pending_link",
                "type": "string",
                "size": "s",
                "description": "Email waiting to be linked to an auth user",
                "required": False,
                "unique": True,
            })

        if "_user_prev" not in existing_field_names:
            concept["fields"].append({
                "name": "_user_prev",
                "type": "string",
                "size": "s",
                "description": "Previous auth user id when this profile was deactivated",
                "required": False,
                "unique": False,
            })

        if "_user_email_prev" not in existing_field_names:
            concept["fields"].append({
                "name": "_user_email_prev",
                "type": "string",
                "size": "s",
                "description": "Previous auth user email kept for audit on deactivation",
                "required": False,
                "unique": False,
            })

    def _validate_profile_autocreate_defaults(self, concept: Dict[str, Any], role_name: str):
        for field in concept["fields"]:
            field_name = field["name"]
            if field_name in ("_user", "_user_email", "_user_pending_link", "_user_prev", "_user_email_prev"):
                continue
            if field["type"] == "relation_to_many":
                continue
            if "calculated" in field:
                continue
            if not field["required"]:
                continue
            if "default" in field:
                continue
            raise ValueError(
                f"Profile concept '{concept['name']}' for role '{role_name}' cannot be "
                f"auto-created because required field '{field_name}' has no default"
            )

    def _expand_prefill_fields(self):
        """Expand prefill fields into individual sub-fields before field processing.

        Replaces each field with type 'prefill' in a concept with a set of sub-fields
        copied from the referenced source concept (with a name prefix). Also stores
        group metadata in concept['_prefill_groups'] for frontend code generation.
        """
        for concept in self.concepts:
            prefill_fields = [f for f in concept["fields"] if f["type"] == "prefill"]
            if not prefill_fields:
                continue

            concept_prefill_groups = []
            new_fields = list(concept["fields"])

            for pfield in prefill_fields:
                subtype = pfield.get("subtype", "")
                parts = subtype.split(".")
                if len(parts) != 2:
                    raise ValueError(
                        f"Field '{pfield['name']}' in concept '{concept['name']}': "
                        f"prefill subtype must be '<concept_name>.<plural_name>', got '{subtype}'"
                    )
                parent_concept_name, child_plural_name = parts

                # Find source concept: plural_name matches AND has part_of -> parent
                source_concept = None
                source_part_of_field_name = None
                for c in self.concepts:
                    if c.get("plural_name") != child_plural_name:
                        continue
                    for f in c["fields"]:
                        if (f["type"] == "relation_to_one"
                                and f.get("subtype") == "part_of"
                                and f["target"] == parent_concept_name):
                            source_concept = c
                            source_part_of_field_name = f["name"]
                            break
                    if source_concept:
                        break

                if not source_concept:
                    raise ValueError(
                        f"Field '{pfield['name']}' in concept '{concept['name']}': "
                        f"cannot find concept with plural_name='{child_plural_name}' "
                        f"that is part_of '{parent_concept_name}'"
                    )

                prefix = pfield["name"]

                # Find the FK in the current concept that points to parent_concept
                parent_fk_in_form = None
                for f in concept["fields"]:
                    if f["type"] == "relation_to_one" and f["target"] == parent_concept_name:
                        parent_fk_in_form = f["name"]
                        break

                if not parent_fk_in_form:
                    raise ValueError(
                        f"Field '{pfield['name']}' in concept '{concept['name']}': "
                        f"no relation_to_one field targeting '{parent_concept_name}' found"
                    )

                # Presentation ID fields of source concept (used for save dialog)
                pres_fields = source_concept["id_presentation"]["fields"]
                pres_field = next((f for f in pres_fields if "." not in f), None)

                # Fields excluded from expansion
                excluded_names = {source_part_of_field_name, "part_of_order", "state", "state_info", "id"}

                # Build expanded fields from source concept fields
                expanded_fields = []
                expanded_field_names = []
                expanded_name_by_source = {}
                for sf in source_concept["fields"]:
                    sf_name = sf["name"]
                    if sf_name in excluded_names or sf_name.startswith("_"):
                        continue
                    if sf["type"] in ("relation_to_one", "relation_to_many"):
                        continue
                    if "calculated" in sf:
                        continue

                    new_field = dict(sf)
                    new_field["name"] = f"{prefix}_{sf_name}"
                    new_field["required"] = sf["required"] if pfield["required"] and sf_name != pres_field else False
                    new_field["unique"] = False
                    new_field["_prefill_group"] = prefix
                    new_field["_prefill_source_field"] = sf_name
                    new_field["_prefill_is_pres_field"] = (sf_name == pres_field)

                    expanded_fields.append(new_field)
                    expanded_field_names.append(new_field["name"])
                    expanded_name_by_source[sf_name] = new_field["name"]

                for validation in self._validations_by_concept.get(source_concept["name"], []):
                    if not all(column in expanded_name_by_source for column in validation["columns"]):
                        continue
                    derived_validation = {
                        "name": f"{validation['name']}-{prefix}",
                        "concept": concept["name"],
                        "columns": [expanded_name_by_source[column] for column in validation["columns"]],
                        "rows": validation["rows"],
                    }
                    self._add_validation(derived_validation)
                    for index, field_name in enumerate(derived_validation["columns"]):
                        for expanded_field in expanded_fields:
                            if expanded_field["name"] == field_name:
                                expanded_field["_validation_csv_filename"] = f"{validation['name']}.csv"
                                expanded_field["_validation_csv_column"] = index
                                break

                concept_prefill_groups.append({
                    "name": prefix,
                    "source_concept": source_concept["name"],
                    "source_concept_plural": child_plural_name,
                    "parent_concept": parent_concept_name,
                    "parent_fk_in_form": parent_fk_in_form,
                    "source_part_of_field": source_part_of_field_name,
                    "presentation_fields": pres_fields,
                    "pres_field": pres_field,
                    "field_names": expanded_field_names,
                })

                # Replace the prefill field with the expanded fields
                idx = new_fields.index(pfield)
                new_fields = new_fields[:idx] + expanded_fields + new_fields[idx + 1:]

            concept["fields"] = new_fields
            if concept_prefill_groups:
                concept["_prefill_groups"] = concept_prefill_groups

    def _process_concept_basics(self, concept: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add basic concept-level metadata and reorder keys.
        Returns a new dictionary with _type inserted early.
        """
        name = concept["name"]
        
        # Validate uniqueness of part_of
        part_of_fields = [f for f in concept["fields"] 
                          if f["type"] == "relation_to_one" and f.get("subtype") == "part_of"]
        
        if len(part_of_fields) > 1:
             raise ValueError(f"Concept '{name}' can only have one 'part_of' relationship, found {len(part_of_fields)}.")
        
        part_of_field = part_of_fields[0] if part_of_fields else None

        # 1. Determine Type (Archetype)
        c_type = self._determine_concept_type(concept)

        # Add recursive check if needed
        if c_type == 'recursive_part_of' and part_of_field:
             if "checks" not in concept:
                 concept["checks"] = []
             concept["checks"].append(f'id != "{part_of_field["name"]}"')

        # 2. Add part_of_order for part_of concepts
        if c_type in ['part_of', 'recursive_part_of']:
             # Add part_of_order field if not exists
             if not any(f["name"] == "part_of_order" for f in concept["fields"]):
                 concept["fields"].append({
                     "name": "part_of_order",
                     "type": "integer",
                     "description": "Auto-generated order for part_of items",
                     "required": False,
                     "unique": False,
                     "size": "s"
                 })

        # 3. Reconstruct dictionary to enforce order
        new_concept = {}

        # Keys to keep at the very top
        top_keys = ['name', 'plural_name', 'description']
        for k in top_keys:
            if k in concept:
                new_concept[k] = concept[k]

        new_concept["_type"] = c_type

        # documents defaults were already applied in process() before this call

        # Insert remaining keys
        for k, v in concept.items():
            if k not in top_keys:
                new_concept[k] = v
        
        return new_concept

    def _process_presentation_logic(self, concept: Dict[str, Any]):
        """
        Calculate presentation mode and expression.
        """
        presentation_config = concept["id_presentation"]
        
        # Default defaults
        mode = "none"
        expr = ""
        
        if 'fields' in presentation_config:
            presentation_fields = presentation_config["fields"]
            if presentation_fields:
                # Check complexity
                is_complex = any('.' in f for f in presentation_fields)
                
                if is_complex:
                    mode = "trigger"
                else:
                    mode = "generated_column"
                    # Build SQL expression for generated column
                    field_refs = []
                    for field_name in presentation_fields:
                        if field_name == "id":
                            field_refs.append("""COALESCE("id"::TEXT, '')""")
                            continue
                            
                        # Find field definition
                        field = next((f for f in concept["fields"] if f["name"] == field_name), None)
                        if field:
                            ftype = field["type"]
                            # Determine cast based on type
                            if ftype in ['string', 'enum']:
                                # Already text, just coalesce
                                field_refs.append(f"""COALESCE("{field_name}", '')""")
                            else:
                                # Needs cast
                                field_refs.append(f"""COALESCE("{field_name}"::TEXT, '')""")
                        else:
                            # Fallback for unknown fields (shouldn't happen in simple mode)
                            field_refs.append(f"""COALESCE("{field_name}"::TEXT, '')""")
                    
                    if field_refs:
                        separator = presentation_config["separator"]
                        separator = separator.replace("'", "''") # Escape for SQL
                        expr = f" || '{separator}' || ".join(field_refs)
        
        concept["_be_presentation_mode"] = mode
        concept["_be_presentation_expr"] = expr

    def _determine_concept_type(self, concept: Dict[str, Any]) -> str:
        """
        Determine the concept archetype: 'root', 'part_of', or 'recursive_part_of'.
        """
        name = concept["name"]
        
        # Check for part_of relationships
        for field in concept["fields"]:
            if field["type"] == "relation_to_one" and field["subtype"] == "part_of":
                target = field["target"]
                if target == name:
                    return 'recursive_part_of'
                return 'part_of'
        
        return 'root'

    def _process_field(self, field: Dict[str, Any], concept: Dict[str, Any]):
        """Enrich a single field."""
        if 'calculated' in field and 'default' in field:
            raise ValueError(
                f"Field '{field['name']}' in concept '{concept['name']}' has both "
                f"'calculated' and 'default' set. Calculated fields cannot have defaults."
            )

        # 1. Backend Processing
        field["_be_sql_type"] = self._determine_sql_type(field)
        field["_be_not_null"] = field["required"]
        
        # 2. Frontend Processing
        field["_fe_visibility"] = self._determine_visibility(field)
        field["_fe_component"] = self._determine_ui_component(field)
        field["_fe_list_component"] = self._determine_list_component(field)
        field["_fe_grid_width"] = 6 if field["size"] in ['m', 'l'] else 3

    def _determine_sql_type(self, field: Dict[str, Any]) -> str:
        """Map abstract type to PostgreSQL type."""
        field_type = field["type"]
        field_name = field["name"]
        
        if field_name == "part_of_order":
            return "SERIAL"
            
        if field_name == "state_info":
            return "JSONB"

        if field_name in ("_user", "_user_prev"):
            return "UUID"

        if field_type == "relation_to_many":
            return "" # Handled via join tables
            
        type_mapping = {
            'string': 'TEXT',
            'integer': 'INTEGER',
            'decimal': 'DECIMAL',
            'boolean': 'BOOLEAN',
            'date': 'DATE',
            'datetime': 'TIMESTAMP WITH TIME ZONE',
            'enum': 'TEXT',
            'relation_to_one': 'INTEGER'
        }
        
        base_type = type_mapping.get(field_type, 'TEXT')
        
        if field_type == "string":
            field_size = field["size"]
            if field_size == "s":
                return 'VARCHAR(255)'
            return 'TEXT' # m, l, or default
            
        if field_type == "decimal":
            precision = field.get("precision", 10)
            scale = field.get("scale", 2)
            return f"DECIMAL({precision}, {scale})"
            
        return base_type

    def _determine_visibility(self, field: Dict[str, Any]) -> str:
        """Determine field visibility: 'editable', 'read_only', 'hidden'."""
        if 'calculated' in field:
            return 'read_only'
            
        if field["name"] == "id":
            return 'read_only' 
            
        if field["name"] == "state":
            return 'internal'

        if field["name"] == "part_of_order":
            return 'internal'
            
        if field["name"] == "state_info":
            return 'internal'

        if field["name"].startswith("_"):
            return 'internal'

        return 'editable'

    def _determine_ui_component(self, field: Dict[str, Any]) -> str:
        """Map field type to React-Admin Input component."""
        if field.get("_validation_csv_filename") and field["type"] == "string":
            return 'RelatedValidationInput'
        mapping = {
            'string': 'TextInput',
            'integer': 'NumberInput',
            'decimal': 'NumberInput',
            'boolean': 'BooleanInput',
            'date': 'DateInput',
            'datetime': 'DateInput',
            'enum': 'SelectInput',
            'relation_to_one': 'ReferenceInput',
            'relation_to_many': 'ReferenceManyField'
        }
        return mapping.get(field["type"], 'TextInput')

    def _determine_list_component(self, field: Dict[str, Any]) -> str:
        """Map field type to React-Admin Field component (for lists/show)."""
        mapping = {
            'string': 'TextField',
            'integer': 'NumberField',
            'decimal': 'NumberField',
            'boolean': 'BooleanField',
            'date': 'DateField',
            'datetime': 'DateField',
            'enum': 'TextField', # Or ChipField
            'relation_to_one': 'ReferenceField',
            'relation_to_many': 'ReferenceManyField' # Usually not shown in simple lists
        }
        return mapping.get(field["type"], 'TextField')

    def _process_relationships(self, concept: Dict[str, Any]):
        """Process Owned Children and M2M Links."""
        concept_name = concept["name"]
        
        # 1. Owned Children (Frontend Focus: Nesting)
        # One-to-Many where 'part_of' is true on child
        owned_children = []
        
        for potential_child in self.concepts:
            child_name = potential_child["name"]
            
            # Check fields
            for field in potential_child["fields"]:
                if (field["type"] == "relation_to_one" and 
                    field["target"] == concept_name and 
                    field["subtype"] == "part_of"):
                    
                    owned_children.append({
                        'child_concept': child_name,
                        'child_fk_field': field["name"],
                        'child_plural': potential_child["plural_name"]
                    })
        
        concept["_fe_owned_children"] = owned_children

        # 2. Many-to-Many Links
        m2m_links = []
        
        # A. Where I am the source
        for field in concept["fields"]:
            if field["type"] == "relation_to_many":
                target_name = field["target"]
                target_concept = self.concept_map.get(target_name)
                if target_concept:
                    is_one_to_many = False
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept_name:
                             is_one_to_many = True
                             break
                    
                    if not is_one_to_many:
                        table1 = concept_name
                        table2 = target_name
                        join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        m2m_links.append({
                            'target_concept': target_name,
                            'join_table': join_table,
                            'my_fk': f"{concept_name}_id",
                            'other_fk': f"{target_name}_id",
                            'field_name': field["name"],
                            'is_source': True
                        })



        # C. Where I am the target
        for other_concept in self.concepts:
            other_name = other_concept["name"]
            if other_name == concept_name:
                continue

            for field in other_concept["fields"]:
                if field["type"] == "relation_to_many" and field["target"] == concept_name:
                    is_one_to_many = False
                    for my_field in concept["fields"]:
                        if my_field["type"] == "relation_to_one" and my_field["target"] == other_name:
                            is_one_to_many = True
                            break
                    
                    if not is_one_to_many:
                        table1 = other_name
                        table2 = concept_name
                        join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        m2m_links.append({
                            'target_concept': other_name,
                            'join_table': join_table,
                            'my_fk': f"{concept_name}_id",
                            'other_fk': f"{other_name}_id",
                            'field_name': other_concept["plural_name"],
                            'is_source': False
                        })


        
        concept["_meta_m2m_links"] = m2m_links
