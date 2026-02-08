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
    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize the Schema Processor.
        
        Args:
            schema: The raw loaded business schema.
        """
        self.raw_schema = schema
        # We work on a deep copy to avoid mutating the original
        self.extended_schema = copy.deepcopy(schema)
        self.concepts = self.extended_schema['concepts']
        self.concept_map = {c['name']: c for c in self.concepts}

    def process(self) -> Dict[str, Any]:
        """
        Enrich the schema with internal metadata.
        
        Returns:
            The extended schema dictionary.
        """
        # Pass 1: Local Concept Processing (Fields, Basic Metadata)
        # We need to iterate by index to modify the list in place with a reordered dict
        for idx, concept in enumerate(self.concepts):
            # Process basics returns a NEW dict with reordered keys
            new_concept = self._process_concept_basics(concept)
            
            # Enrich with presentation logic
            self._process_presentation_logic(new_concept)
            
            # Update the reference in the list
            self.concepts[idx] = new_concept
            
            # Process fields (fields are inside the new_concept now)
            for field in new_concept['fields']:
                self._process_field(field, new_concept)
        
        # Pass 2: Cross-Concept Processing (Relationships)
        for concept in self.concepts:
            self._process_relationships(concept)

        return self.extended_schema

    def _process_concept_basics(self, concept: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add basic concept-level metadata and reorder keys.
        Returns a new dictionary with _type inserted early.
        """
        name = concept['name']
        
        # 1. Determine Type (Archetype)
        c_type = self._determine_concept_type(concept)
        
        # 2. Reconstruct dictionary to enforce order
        new_concept = {}
        
        # Keys to keep at the very top
        top_keys = ['name', 'plural_name', 'description']
        for k in top_keys:
            if k in concept:
                new_concept[k] = concept[k]
        
        # Insert _type here
        new_concept['_type'] = c_type
        
        # Insert remaining keys
        for k, v in concept.items():
            if k not in top_keys:
                new_concept[k] = v
        
        return new_concept

    def _process_presentation_logic(self, concept: Dict[str, Any]):
        """
        Calculate presentation mode and expression.
        """
        presentation_config = concept.get('id_presentation')
        
        # Default defaults
        mode = "none"
        expr = ""
        
        if presentation_config and 'fields' in presentation_config:
            presentation_fields = presentation_config['fields']
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
                        if field_name == 'id':
                            field_refs.append("""COALESCE("id"::TEXT, '')""")
                            continue
                            
                        # Find field definition
                        field = next((f for f in concept['fields'] if f['name'] == field_name), None)
                        if field:
                            ftype = field['type']
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
                        separator = presentation_config.get('separator', ' ')
                        separator = separator.replace("'", "''") # Escape for SQL
                        expr = f" || '{separator}' || ".join(field_refs)
        
        concept['_be_presentation_mode'] = mode
        if expr:
            concept['_be_presentation_expr'] = expr

    def _determine_concept_type(self, concept: Dict[str, Any]) -> str:
        """
        Determine the concept archetype: 'root', 'part_of', or 'recursive_part_of'.
        """
        name = concept['name']
        
        # Check for part_of relationships
        for field in concept['fields']:
            if field['type'] == 'relation_to_one' and field.get('subtype') == 'part_of':
                target = field['target']
                if target == name:
                    return 'recursive_part_of'
                return 'part_of'
        


        return 'root'

    def _process_field(self, field: Dict[str, Any], concept: Dict[str, Any]):
        """Enrich a single field."""
        
        # 1. Backend Processing
        field['_be_sql_type'] = self._determine_sql_type(field)
        field['_be_not_null'] = self._determine_required(field, concept)
        
        # 2. Frontend Processing
        field['_fe_visibility'] = self._determine_visibility(field)
        field['_fe_component'] = self._determine_ui_component(field)
        field['_fe_list_component'] = self._determine_list_component(field)
        field['_fe_grid_width'] = 6 if field.get('size') in ['m', 'l'] else 3

    def _determine_sql_type(self, field: Dict[str, Any]) -> str:
        """Map abstract type to PostgreSQL type."""
        field_type = field['type']
        
        if field_type == 'relation_to_many':
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
        
        if field_type == 'string':
            field_size = field.get('size')
            if field_size == 's':
                return 'VARCHAR(255)'
            return 'TEXT' # m, l, or default
            
        if field_type == 'decimal':
            precision = field.get('precision', 10)
            scale = field.get('scale', 2)
            return f"DECIMAL({precision}, {scale})"
            
        return base_type

    def _determine_required(self, field: Dict[str, Any], concept: Dict[str, Any]) -> bool:
        """Determine if a field is NOT NULL in DB."""
        is_required = field.get('required')
        
        if is_required is not None:
            return is_required
            
        # Default logic
        if field['type'] == 'relation_to_one' and field.get('subtype') == 'part_of':
            # Self-reference usually implies nullable root
            if field.get('target') == concept['name']:
                return False
            return True
            
        return False

    def _determine_visibility(self, field: Dict[str, Any]) -> str:
        """Determine field visibility: 'editable', 'read_only', 'hidden'."""
        if 'calculated' in field:
            return 'read_only'
            
        if field['name'] == 'id':
            return 'read_only' 
            
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
        return mapping.get(field['type'], 'TextInput')

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
        return mapping.get(field['type'], 'TextField')

    def _process_relationships(self, concept: Dict[str, Any]):
        """Process Owned Children and M2M Links."""
        concept_name = concept['name']
        
        # 1. Owned Children (Frontend Focus: Nesting)
        # One-to-Many where 'part_of' is true on child
        owned_children = []
        
        for potential_child in self.concepts:
            child_name = potential_child['name']
            
            # Check fields
            for field in potential_child['fields']:
                if (field['type'] == 'relation_to_one' and 
                    field['target'] == concept_name and 
                    field.get('subtype') == 'part_of'):
                    
                    owned_children.append({
                        'child_concept': child_name,
                        'child_fk_field': field['name'],
                        'child_plural': potential_child.get('plural_name', f"{child_name}s")
                    })
            

        
        concept['_fe_owned_children'] = owned_children

        # 2. Many-to-Many Links
        m2m_links = []
        
        # A. Where I am the source
        for field in concept['fields']:
            if field['type'] == 'relation_to_many':
                target_name = field['target']
                target_concept = self.concept_map.get(target_name)
                if target_concept:
                    is_one_to_many = False
                    for target_field in target_concept['fields']:
                        if target_field['type'] == 'relation_to_one' and target_field['target'] == concept_name:
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
                            'field_name': field['name'],
                            'is_source': True
                        })



        # C. Where I am the target
        for other_concept in self.concepts:
            other_name = other_concept['name']
            if other_name == concept_name:
                continue

            for field in other_concept['fields']:
                if field['type'] == 'relation_to_many' and field['target'] == concept_name:
                    is_one_to_many = False
                    for my_field in concept['fields']:
                        if my_field['type'] == 'relation_to_one' and my_field['target'] == other_name:
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
                            'field_name': other_concept.get('plural_name', f"{other_name}s"),
                            'is_source': False
                        })


        
        concept['_meta_m2m_links'] = m2m_links
