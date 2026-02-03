"""
Supabase Schema Generation Module

Generates PostgreSQL database schema for Supabase from business concept definitions.
"""

from typing import Dict, Any, List, Tuple
from .schema_loader import SchemaLoader
import logging
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)

class SupabaseGenerator:
    def __init__(self, schema_loader: SchemaLoader):
        """
        Initialize the Supabase generator.
        
        Args:
            schema_loader: SchemaLoader instance with loaded business schema
        """
        self.schema_loader = schema_loader
        self.concepts = schema_loader.get_all_concepts()
        self.concept_map = {concept['name']: concept for concept in self.concepts}
    
    def generate_sql_schema(self) -> str:
        """
        Generate complete SQL schema for Supabase.
        
        Returns:
            SQL statements as a string
        """
        sql_parts = []
        
        # Generate tables for each concept
        for concept in self.concepts:
            table_sql = self._generate_table_sql(concept)
            sql_parts.append(table_sql)
        
        # Generate join tables for many-to-many relationships
        join_tables = self._generate_join_tables()
        sql_parts.extend(join_tables)
        
        # Generate foreign key constraints
        fk_constraints = self._generate_foreign_key_constraints()
        sql_parts.extend(fk_constraints)

        # Generate presentation triggers
        presentation_triggers = self._generate_presentation_triggers()
        sql_parts.extend(presentation_triggers)
        
        return '\n\n'.join(sql_parts)
    
    def _generate_table_sql(self, concept: Dict[str, Any]) -> str:
        """
        Generate SQL for a single concept table.
        
        Args:
            concept: Concept definition
            
        Returns:
            SQL CREATE TABLE statement
        """
        table_name = concept['name']
        
        # Start with table creation
        sql_lines = [f'CREATE TABLE "{table_name}" (']
        sql_lines.append('  "id" SERIAL PRIMARY KEY,')
        
        # Add fields
        for field in concept['fields']:
            field_sql = self._generate_field_sql(field)
            sql_lines.append(f"  {field_sql},")
        
        # Add id_presentation column if presentation_id is defined
        trigger_sql = ""
        presentation_config = concept.get('presentation_id')
        if presentation_config and 'fields' in presentation_config:
            presentation_fields = presentation_config['fields']
            if presentation_fields:
                # Check if complex (recursive/relationships)
                is_complex = False
                for field_name in presentation_fields:
                    if '.' in field_name:
                        is_complex = True
                        break
                
                if not is_complex:
                    # Simple case: use generated column
                    field_refs = []
                    for field_name in presentation_fields:
                        # Check if field exists in the concept
                        field_exists = any(field['name'] == field_name for field in concept['fields'])
                        if field_exists:
                            # Find the field to get its type
                            field = next(field for field in concept['fields'] if field['name'] == field_name)
                            field_type = field['type']
                            
                            # Convert non-text fields to text
                            if field_type in ['integer', 'decimal', 'boolean', 'date', 'datetime']:
                                field_refs.append(f'COALESCE("{field_name}"::TEXT, \'\')')
                            else:
                                field_refs.append(f'COALESCE("{field_name}", \'\')')
                        else:
                            # Handle relationship fields (e.g., "product" in order_item)
                            # For now, we'll skip them as they require joins
                            pass
                
                    if field_refs:
                        # Create the concatenated expression
                        separator = presentation_config.get('separator', ' ')
                        # Escape single quotes in separator
                        separator = separator.replace("'", "''")
                        concat_expr = f" || '{separator}' || ".join(field_refs)
                        sql_lines.append(f'  "id_presentation" TEXT GENERATED ALWAYS AS ({concat_expr}) STORED,')
                else:
                    # Complex case: use trigger (generated later)
                    sql_lines.append(f'  "id_presentation" TEXT,')
        
        # Add created_at and updated_at timestamps
        sql_lines.append('  "created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,')
        sql_lines.append('  "updated_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP')
        
        # Close table definition
        sql_lines.append(');')
        
        # Add trigger to update updated_at timestamp on row updates
        trigger_name = f"{table_name}_update_updated_at"
        sql_lines.append(f"""
CREATE OR REPLACE FUNCTION "update_{table_name}_updated_at"()
RETURNS TRIGGER AS $$BEGIN
    NEW."updated_at" = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "{trigger_name}"
BEFORE UPDATE ON "{table_name}"
FOR EACH ROW
EXECUTE FUNCTION "update_{table_name}_updated_at"();
""")

        # Add unique constraints
        unique_fields = [field for field in concept['fields'] if field.get('unique', False)]
        for field in unique_fields:
            field_name = field['name']
            constraint_name = f"{table_name}_{field_name}_unique"
            sql_lines.append(f'CREATE UNIQUE INDEX "{constraint_name}" ON "{table_name}" ("{field_name}");')
        
        return '\n'.join(sql_lines)
    
    def _generate_field_sql(self, field: Dict[str, Any]) -> str:
        """
        Generate SQL for a single field.
        
        Args:
            field: Field definition
            
        Returns:
            SQL field definition
        """
        field_name = field['name']
        field_type = field['type']
        
        # Map field types to PostgreSQL types
        type_mapping = {
            'string': 'TEXT',
            'integer': 'INTEGER',
            'decimal': 'DECIMAL',
            'boolean': 'BOOLEAN',
            'date': 'DATE',
            'datetime': 'TIMESTAMP WITH TIME ZONE',
            'enum': 'TEXT'
        }
        
        base_type = type_mapping.get(field_type, 'TEXT')
        
        # Handle text field sizes
        if field_type == 'string':
            field_size = field.get('size')
            if field_size == 's':
                sql_type = 'VARCHAR(255)'  # Small text fields
            elif field_size == 'm':
                sql_type = 'TEXT'  # Medium text fields (default)
            elif field_size == 'l':
                sql_type = 'TEXT'  # Large text fields (same as medium but can be handled differently in UI)
            else:
                sql_type = base_type
        else:
            sql_type = base_type
        
        # Handle special cases
        if field_type == 'decimal':
            precision = field.get('precision', 10)
            scale = field.get('scale', 2)
            sql_type = f"DECIMAL({precision}, {scale})"
        elif field_type == 'enum':
            sql_type = 'TEXT'  # We'll add CHECK constraint later
        
        # Build field definition
        field_parts = [f'"{field_name}" {sql_type}']
        
        # Add constraints
        if field.get('required', False):
            field_parts.append("NOT NULL")
        
        if 'default' in field:
            default_value = field['default']
            if isinstance(default_value, str):
                field_parts.append(f"DEFAULT '{default_value}'")
            elif isinstance(default_value, (int, float)):
                field_parts.append(f"DEFAULT {default_value}")
            elif isinstance(default_value, bool):
                field_parts.append(f"DEFAULT {str(default_value).upper()}")
        
        # Add enum constraints
        if field_type == 'enum' and 'enum_values' in field:
            allowed_values = ', '.join([f"'{value}'" for value in field['enum_values']])
            constraint_name = f"{field_name}_enum_check"
            field_parts.append(f"CONSTRAINT {constraint_name} CHECK ({field_name} IN ({allowed_values}))")
        
        return ' '.join(field_parts)
    
    def _generate_join_tables(self) -> List[str]:
        """
        Generate join tables for many-to-many relationships.
        
        Returns:
            List of SQL CREATE TABLE statements for join tables
        """
        join_tables = []
        
        for concept in self.concepts:
            if 'relationships' not in concept:
                continue
            
            for relationship in concept['relationships']:
                if relationship['type'] == 'many-to-many':
                    target_concept = relationship['target']
                    
                    # Create join table name (alphabetical order to avoid duplicates)
                    table1 = concept['name']
                    table2 = target_concept
                    join_table_name = f"{min(table1, table2)}_{max(table1, table2)}"
                    
                    # Only create the join table once
                    if join_table_name not in [jt.split('(')[0].strip() for jt in join_tables]:
                        sql = f"""
CREATE TABLE "{join_table_name}" (
  "{table1}_id" INTEGER NOT NULL,
  "{table2}_id" INTEGER NOT NULL,
  "created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("{table1}_id", "{table2}_id"),
  FOREIGN KEY ("{table1}_id") REFERENCES "{table1}"("id") ON DELETE CASCADE,
  FOREIGN KEY ("{table2}_id") REFERENCES "{table2}"("id") ON DELETE CASCADE
);
"""
                        join_tables.append(sql)
        
        return join_tables
    
    def _generate_foreign_key_constraints(self) -> List[str]:
        """
        Generate foreign key constraints for relationships.
        
        Returns:
            List of SQL ALTER TABLE statements for foreign keys
        """
        fk_constraints = []
        
        for concept in self.concepts:
            if 'relationships' not in concept:
                continue
            
            table_name = concept['name']
            
            for relationship in concept['relationships']:
                if relationship['type'] in ['belongs-to', 'one-to-many']:
                    target_concept = relationship['target']
                    target_table = target_concept
                    
                    # Determine field name
                    if 'field_name' in relationship:
                        field_name = relationship['field_name']
                    else:
                        # Default field name based on target concept
                        field_name = f"{target_table}_id"
                    
                    # Create foreign key constraint
                    constraint_name = f"fk_{table_name}_{field_name}"
                    
                    # For belongs-to relationships, add the foreign key to the current table
                    if relationship['type'] == 'belongs-to':
                        not_null_clause = " NOT NULL" if relationship.get('required', False) else ""
                        fk_sql = f"""
ALTER TABLE "{table_name}"
  ADD COLUMN IF NOT EXISTS "{field_name}" INTEGER{not_null_clause},
  ADD CONSTRAINT "{constraint_name}"
  FOREIGN KEY ("{field_name}") REFERENCES "{target_table}"("id");"""
                        fk_constraints.append(fk_sql)
                    
                    # For one-to-many relationships, we might need to add the foreign key to the target table
                    # This is more complex and would require analyzing the inverse relationship
        
        return fk_constraints
    
    def generate_sample_data_sql(self) -> str:
        """
        Generate SQL for inserting sample data.
        
        Returns:
            SQL INSERT statements as a string
        """
        sql_parts = []
        
        # Topological sort of concepts to ensure foreign key dependencies are met
        sorted_concepts = []
        visited = set()
        
        def visit(concept_name):
            if concept_name in visited:
                return
            
            concept = self.concept_map.get(concept_name)
            if not concept:
                return
                
            # Visit dependencies first
            if 'relationships' in concept:
                for relationship in concept['relationships']:
                    if relationship['type'] == 'belongs-to':
                        target_concept = relationship['target']
                        if target_concept != concept_name:
                            visit(target_concept)
            
            visited.add(concept_name)
            sorted_concepts.append(concept)

        for concept in self.concepts:
            visit(concept['name'])
            
        for concept in sorted_concepts:
            sample_data = self._generate_sample_data_for_concept(concept)
            if sample_data:
                sql_parts.append(sample_data)
        
        return '\n\n'.join(sql_parts)
    
    def _generate_sample_data_for_concept(self, concept: Dict[str, Any]) -> str:
        """
        Generate sample data for a single concept.
        
        Args:
            concept: Concept definition
            
        Returns:
            SQL INSERT statements
        """
        table_name = concept['name']
        
        # Generate 3 sample records
        sample_records = []
        
        for i in range(1, 4):
            field_values = []
            field_names = []
            
            for field in concept['fields']:
                field_name = field['name']
                field_type = field['type']
                
                # Generate sample value based on type
                if field_type == 'string':
                    if field_name == 'email':
                        value = f"'{field_name}{i}@example.com'"
                    elif field_name == 'sku':
                        value = f"'SKU-{i:03d}'"
                    else:
                        value = f"'{field_name}_sample_{i}'"
                elif field_type == 'integer':
                    value = str(i * 10)
                elif field_type == 'decimal':
                    value = f"{i * 10}.{i:02d}"
                elif field_type == 'boolean':
                    value = 'TRUE' if i % 2 == 0 else 'FALSE'
                elif field_type == 'enum':
                    enum_values = field.get('enum_values', ['value1', 'value2'])
                    value = f"'{enum_values[0]}'"
                elif field_type == 'date':
                    value = f"'2023-01-{i:02d}'"
                elif field_type == 'datetime':
                    value = f"'2023-01-{i:02d}T10:00:00Z'"
                else:
                    value = f"'{field_name}_value_{i}'"
                
                field_names.append(field_name)
                field_values.append(value)
            
            # Add timestamps
            field_names.extend(['created_at', 'updated_at'])
            field_values.extend([f"'2023-01-{i:02d}T10:00:00Z'", f"'2023-01-{i:02d}T10:00:00Z'"])
            
            # Add foreign keys for belongs-to relationships
            if 'relationships' in concept:
                for relationship in concept['relationships']:
                    if relationship['type'] == 'belongs-to':
                        field_name = relationship.get('field_name', f"{relationship['target']}_id")
                        field_names.append(field_name)
                        
                        if relationship['target'] == concept['name']:
                             # For self-references, use NULL to avoid constraint violations during insert
                             # (and to represent root nodes)
                             field_values.append('NULL')
                        else:
                            # Assume referenced tables have IDs 1, 2, 3...
                            # Use modulo to distribute relationships if needed, or just match i
                            # To be safe, just point to ID 1 or i (assuming referenced data exists)
                            # Since we generate 3 records for everything, i (1,2,3) should be safe.
                            field_values.append(str(i))

            fields_str = ', '.join([f'"{field_name}"' for field_name in field_names])
            values_str = ', '.join(field_values)
            
            sample_records.append(f"({values_str})")
        
        if not sample_records:
            return ""
        
        return f'INSERT INTO "{table_name}" ({fields_str}) VALUES\n' + ",\n".join(sample_records) + ";"

    def _generate_presentation_triggers(self) -> List[str]:
        """
        Generate triggers for complex presentation_id_fields.
        
        Returns:
            List of SQL statements for triggers
        """
        triggers = []
        
        for concept in self.concepts:
            presentation_config = concept.get('presentation_id')
            if not presentation_config or 'fields' not in presentation_config:
                continue
                
            presentation_fields = presentation_config['fields']
            if not presentation_fields:
                continue
                
            # Check if complex
            is_complex = False
            for field_name in presentation_fields:
                if '.' in field_name:
                    is_complex = True
                    break
            
            if not is_complex:
                continue
                
            # Generate Trigger
            table_name = concept['name']
            declarations = []
            selects = []
            parts = []
            
            for idx, field_name in enumerate(presentation_fields):
                part_var = f"part_{idx}"
                
                if '.' in field_name:
                    # Remote field: rel.field
                    rel_name, target_field = field_name.split('.', 1)
                    
                    # Find relationship
                    rel = None
                    if 'relationships' in concept:
                        for r in concept['relationships']:
                            if r['type'] == 'belongs-to':
                                fk_col = r.get('field_name', f"{r['target']}_id")
                                # Match by FK name or Target name
                                if fk_col == rel_name or r['target'] == rel_name:
                                    rel = r
                                    break
                    
                    if rel:
                        fk_col = rel.get('field_name', f"{rel['target']}_id")
                        target_table = rel['target']
                        declarations.append(f"{part_var} TEXT;")
                        
                        selects.append(f"""
    IF NEW."{fk_col}" IS NOT NULL THEN
        SELECT "{target_field}"::TEXT INTO {part_var} FROM "{target_table}" WHERE "id" = NEW."{fk_col}";
    END IF;""")
                        parts.append(f"COALESCE({part_var}, '')")
                    else:
                        parts.append("''")
                else:
                    # Local field
                    field_exists = any(f['name'] == field_name for f in concept['fields'])
                    if field_exists:
                        parts.append(f"COALESCE(NEW.\"{field_name}\"::TEXT, '')")
                    else:
                        parts.append("''")
            
            separator = presentation_config.get('separator', ' ')
            # Escape single quotes in separator
            separator = separator.replace("'", "''")
            concat_expr = f" || '{separator}' || ".join(parts)
            
            trigger_sql = f"""

CREATE OR REPLACE FUNCTION "update_{table_name}_id_presentation"()
RETURNS TRIGGER AS $$
DECLARE
    {chr(10).join(declarations)}
BEGIN
    {chr(10).join(selects)}
    NEW."id_presentation" := {concat_expr};
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "{table_name}_update_id_presentation"
BEFORE INSERT OR UPDATE ON "{table_name}"
FOR EACH ROW
EXECUTE FUNCTION "update_{table_name}_id_presentation"();
"""
            triggers.append(trigger_sql)
            
        return triggers
