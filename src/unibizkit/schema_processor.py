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
from typing import Dict, Any, List, Optional

class SchemaProcessor:
    def __init__(self, schema: Dict[str, Any], security_config: Optional[Dict[str, Any]] = None, presentation_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Schema Processor.
        
        Args:
            schema: The raw loaded business schema.
            security_config: The loaded security configuration.
            presentation_config: The loaded presentation configuration.
        """
        self.raw_schema = schema
        self.security_config = security_config or {"authentication_required": False}
        self.security_extended = copy.deepcopy(self.security_config)
        self.presentation_extended = copy.deepcopy(presentation_config or {})
        
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
        # 0. Enrich Security
        self._enrich_security()

        # 1. Pass 1: Local Concept Processing (Fields, Basic Metadata)
        # We need to iterate by index to modify the list in place with a reordered dict
        for idx, concept in enumerate(self.concepts):
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

        return self.extended_schema

    def _enrich_security(self):
        """Inject default roles and users if missing, and expand rule wildcards."""
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

        if not self.security_extended.get("authentication_required"):
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
        
        for concept in self.concepts:
            concept_name = concept["name"]
            concept_acl = {"_main": {}, "_fields": {}}
            
            # 1. Main access (concept-level)
            for role_name in role_names:
                access = rules_map.get((concept_name, "*", role_name))
                if access:
                    concept_acl["_main"][role_name] = access
            
            # 2. Field-level access (explicit for all fields)
            for field in concept["fields"]:
                field_name = field["name"]
                field_rules = {}
                
                # Check each role for this field
                for role_name in role_names:
                    # Specific field rule overrides concept rule
                    access = rules_map.get((concept_name, field_name, role_name))
                    if not access:
                        # Fallback to main rule
                        access = concept_acl["_main"].get(role_name)
                        
                    if access:
                        field_rules[role_name] = access
                
                if field_rules:
                    concept_acl["_fields"][field_name] = field_rules
            
            if concept_acl["_main"] or concept_acl["_fields"]:
                _acl[concept_name] = concept_acl
                
        self.security_extended["_acl"] = _acl

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
        
        # Insert _type and _part_of_field here
        new_concept["_type"] = c_type
        new_concept["_part_of_field"] = part_of_field
        
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
            
        if field["name"] == "part_of_order":
            return 'internal'
            
        return 'editable'

    def _determine_ui_component(self, field: Dict[str, Any]) -> str:
        """Map field type to React-Admin Input component."""
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
