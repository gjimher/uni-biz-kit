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
        
        return '\n\n'.join(sql_parts)
    
    def _generate_table_sql(self, concept: Dict[str, Any]) -> str:
        """
        Generate SQL for a single concept table.
        
        Args:
            concept: Concept definition
            
        Returns:
            SQL CREATE TABLE statement
        """
        table_name = concept['name'].lower()
        
        # Start with table creation
        sql_lines = [f'CREATE TABLE "{table_name}" (']
        sql_lines.append('  "id" SERIAL PRIMARY KEY,')
        
        # Add fields
        for field in concept['fields']:
            field_sql = self._generate_field_sql(field)
            sql_lines.append(f"  {field_sql},")
        
        # Add created_at and updated_at timestamps
        sql_lines.append('  "created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,')
        sql_lines.append('  "updated_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP')
        
        # Close table definition
        sql_lines.append(");")
        
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
        
        # Handle special cases
        if field_type == 'decimal':
            precision = field.get('precision', 10)
            scale = field.get('scale', 2)
            sql_type = f"DECIMAL({precision}, {scale})"
        elif field_type == 'enum':
            sql_type = 'TEXT'  # We'll add CHECK constraint later
        else:
            sql_type = base_type
        
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
        if field_type == 'enum' and 'enumValues' in field:
            allowed_values = ', '.join([f"'{value}'" for value in field['enumValues']])
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
                    table1 = concept['name'].lower()
                    table2 = target_concept.lower()
                    join_table_name = f"{min(table1, table2)}_{max(table1, table2)}"
                    
                    # Only create the join table once
                    if join_table_name not in [jt.split('(')[0].strip() for jt in join_tables]:
                        sql = f"""CREATE TABLE "{join_table_name}" (
  "{table1}_id" INTEGER NOT NULL,
  "{table2}_id" INTEGER NOT NULL,
  "created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("{table1}_id", "{table2}_id"),
  FOREIGN KEY ("{table1}_id") REFERENCES "{table1}"("id") ON DELETE CASCADE,
  FOREIGN KEY ("{table2}_id") REFERENCES "{table2}"("id") ON DELETE CASCADE
);"""
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
            
            table_name = concept['name'].lower()
            
            for relationship in concept['relationships']:
                if relationship['type'] in ['belongs-to', 'one-to-many']:
                    target_concept = relationship['target']
                    target_table = target_concept.lower()
                    
                    # Determine field name
                    if 'fieldName' in relationship:
                        field_name = relationship['fieldName']
                    else:
                        # Default field name based on target concept
                        field_name = f"{target_table}_id"
                    
                    # Create foreign key constraint
                    constraint_name = f"fk_{table_name}_{field_name}"
                    
                    # For belongs-to relationships, add the foreign key to the current table
                    if relationship['type'] == 'belongs-to':
                        fk_sql = f"""ALTER TABLE "{table_name}"
  ADD COLUMN IF NOT EXISTS "{field_name}" INTEGER,
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
        
        for concept in self.concepts:
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
        table_name = concept['name'].lower()
        
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
                    enum_values = field.get('enumValues', ['value1', 'value2'])
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
            
            fields_str = ', '.join([f'"{field_name}"' for field_name in field_names])
            values_str = ', '.join(field_values)
            
            sample_records.append(f"({values_str})")
        
        if not sample_records:
            return ""
        
        return f'INSERT INTO "{table_name}" ({fields_str}) VALUES\n' + ",\n".join(sample_records) + ";"