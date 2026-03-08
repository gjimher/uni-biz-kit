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
        self.concept_map = {concept["name"]: concept for concept in self.concepts}
    
    def generate_sql_schema(self) -> str:
        """
        Generate complete SQL schema for Supabase.
        
        Returns:
            SQL statements as a string
        """
        sql_parts = []

        # Ensure pgcrypto is available for password hashing
        sql_parts.append("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

        # Add generic updated_at function
        sql_parts.append("""
CREATE OR REPLACE FUNCTION update_updated_at_column() 
RETURNS TRIGGER AS $$
BEGIN
    NEW."_updated_at" = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")
        
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
        
        # Generate Security Policies (RLS)
        if self.schema_loader.security_config.get("authentication_required"):
            security_policies = self._generate_security_policies()
            sql_parts.extend(security_policies)
        
        return '\n\n'.join(sql_parts)

    def _generate_security_policies(self) -> List[str]:
        """
        Generate Row Level Security (RLS) policies.
        """
        policies = []
        
        _acl = self.schema_loader.security_config["_acl"]
        roles = self.schema_loader.security_config["roles"]
        all_role_names = set(r["name"] for r in roles)
        
        # Calculate join table names cleanly.
        join_tables = []
        for concept in self.concepts:
            for field in concept["fields"]:
                if field["type"] == "relation_to_many":
                    target_name = field["target"]
                    target_concept = self.concept_map.get(target_name)
                    if not target_concept: continue
                    
                    is_one_to_many = False
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                             is_one_to_many = True
                             break
                    
                    if not is_one_to_many:
                        t1, t2 = concept["name"], target_name
                        jt = f"{min(t1, t2)}_{max(t1, t2)}"
                        if jt not in join_tables:
                            join_tables.append(jt)
        
        all_tables = [c["name"] for c in self.concepts] + join_tables
        
        for table in all_tables:
            policies.append(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            
            concept_acl = _acl.get(table)
            
            if not concept_acl:
                # Fallback: if no rules for this concept (or if it's a join table), allow all authenticated
                policies.append(f"""
CREATE POLICY "allow_all_authenticated_{table}" ON "{table}"
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);
""")
                continue

            # Field-level write restrictions (trigger based)
            concept = self.concept_map.get(table)
            main_rules = concept_acl["_main"]
            if concept:
                trigger_checks = []
                for field in concept["fields"]:
                    field_name = field["name"]
                    field_rules = concept_acl["_fields"].get(field_name, {})
                    
                    allowed_roles = []
                    for role in all_role_names:
                        access = field_rules.get(role, main_rules.get(role, "none"))
                        if access in ("write", "owner_write"):
                            allowed_roles.append(role)
                    
                    # If this field has limited writers
                    if allowed_roles and set(allowed_roles) != all_role_names:
                        roles_json_array = ", ".join(f"'{r}'" for r in allowed_roles)
                        check = f"""
    -- Check field '{field_name}'
    IF (TG_OP = 'UPDATE' AND NEW."{field_name}" IS DISTINCT FROM OLD."{field_name}") OR (TG_OP = 'INSERT' AND NEW."{field_name}" IS NOT NULL) THEN
        IF NOT (user_roles ?| array[{roles_json_array}]) THEN
            RAISE EXCEPTION 'Permission denied for field {field_name}';
        END IF;
    END IF;"""
                        trigger_checks.append(check)
                
                if trigger_checks:
                    trigger_name = f"{table}_field_security"
                    trigger_func = f"""
CREATE OR REPLACE FUNCTION "{trigger_name}_func"()
RETURNS TRIGGER AS $$
DECLARE
    user_roles jsonb := coalesce(auth.jwt() -> 'app_metadata' -> 'roles', '[]'::jsonb);
BEGIN
    -- Bypass trigger for system operations (like seeding data directly)
    IF current_setting('request.jwt.claims', true) IS NULL OR current_setting('request.jwt.claims', true) = '' THEN
        RETURN NEW;
    END IF;
{''.join(trigger_checks)}
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS "{trigger_name}" ON "{table}";
CREATE TRIGGER "{trigger_name}"
BEFORE INSERT OR UPDATE ON "{table}"
FOR EACH ROW
EXECUTE FUNCTION "{trigger_name}_func"();
"""
                    policies.append(trigger_func)

            # Generate table-level RLS policies
            # Determine max access for each role on this table
            role_table_access = {} # role -> max_access
            for role in all_role_names:
                role_table_access[role] = main_rules.get(role, "none")
                
            for field_name, field_rules in concept_acl["_fields"].items():
                for role, access in field_rules.items():
                    current = role_table_access.get(role, "none")
                    if access == "write" or current == "write":
                        role_table_access[role] = "write"
                    elif access == "owner_write" and current not in ("write", "owner_write"):
                        role_table_access[role] = "owner_write"
                    elif access == "read" and current == "none":
                        role_table_access[role] = "read"

            for role, access in role_table_access.items():
                condition = f"auth.jwt() -> 'app_metadata' -> 'roles' ? '{role}'"
                
                if access == "read":
                    policies.append(f"""
CREATE POLICY "{role}_read_{table}" ON "{table}"
FOR SELECT
TO authenticated
USING ({condition});
""")
                elif access == "write":
                    policies.append(f"""
CREATE POLICY "{role}_all_{table}" ON "{table}"
FOR ALL
TO authenticated
USING ({condition})
WITH CHECK ({condition});
""")
                elif access == "owner_write":
                    policies.append(f"""
CREATE POLICY "{role}_owner_all_{table}" ON "{table}"
FOR ALL
TO authenticated
USING ({condition} AND "security_owner_id" = auth.uid()::text)
WITH CHECK ({condition} AND "security_owner_id" = auth.uid()::text);
""")

        return policies

        return policies
    
    def _generate_table_sql(self, concept: Dict[str, Any]) -> str:
        """
        Generate SQL for a single concept table.
        
        Args:
            concept: Concept definition
            
        Returns:
            SQL CREATE TABLE statement
        """
        # Use enriched table name if available, fallback to name
        table_name = concept["name"]
        pk_name = "id"
        
        # Start with table creation
        sql_lines = [f'CREATE TABLE "{table_name}" (']
        sql_lines.append(f'  "{pk_name}" SERIAL PRIMARY KEY,')
        
        # Add fields
        for field in concept["fields"]:
            field_sql = self._generate_field_sql(field, concept)
            if field_sql:
                sql_lines.append(f"  {field_sql},")
        
        # Add id_presentation column based on enriched metadata
        presentation_mode = concept["_be_presentation_mode"]
        
        if presentation_mode == "generated_column":
            expr = concept["_be_presentation_expr"]
            sql_lines.append(f'  "id_presentation" TEXT GENERATED ALWAYS AS ({expr}) STORED,')
        elif presentation_mode == "trigger":
            sql_lines.append(f'  "id_presentation" TEXT,')
        
        # Add created_at and updated_at timestamps
        sql_lines.append('  "_created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,')
        sql_lines.append('  "_updated_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP')
        
        # Close table definition
        sql_lines.append(');')
        
        # Add check constraints
        checks = concept.get('checks', [])
        for i, check_expr in enumerate(checks):
            constraint_name = f"{table_name}_check_{i}"
            sql_lines.append(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" CHECK ({check_expr});')
        
        # Add trigger to update updated_at timestamp on row updates
        trigger_name = f"{table_name}_update_updated_at"
        sql_lines.append(f"""
CREATE TRIGGER "{trigger_name}" 
BEFORE UPDATE ON "{table_name}" 
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
"""
)

        # Add unique constraints
        unique_fields = [field for field in concept["fields"] if field["unique"]]
        for field in unique_fields:
            field_name = field["name"]
            constraint_name = f"{table_name}_{field_name}_unique"
            sql_lines.append(f'CREATE UNIQUE INDEX "{constraint_name}" ON "{table_name}" ("{field_name}");')
        
        return '\n'.join(sql_lines)
    
    def _generate_field_sql(self, field: Dict[str, Any], concept: Dict[str, Any]) -> str:

        """
        Generate SQL for a single field using enriched metadata.
        
        Args:
            field: Field definition
            concept: Concept definition (context)
            
        Returns:
            SQL field definition or empty string if field should be skipped
        """
        field_name = field["name"]
        
        # Use enriched SQL type
        sql_type = field["_be_sql_type"]
        
        if not sql_type:
            # Skip fields without SQL type (e.g., relation_to_many)
            return ""
        
        # Handle Calculated Fields
        if 'calculated' in field:
            expr = field["calculated"]
            sql_parts = [f'"{field_name}" {sql_type} GENERATED ALWAYS AS ({expr}) STORED']
            return ' '.join(sql_parts)

        field_parts = [f'"{field_name}" {sql_type}']
        
        # Use enriched Not Null constraint
        if field["_be_not_null"]:
            field_parts.append("NOT NULL")
        
        # Defaults
        if 'default' in field:
            default_value = field["default"]
            if isinstance(default_value, str):
                if default_value in ("auth.uid()", "auth.uid()::text"):
                    field_parts.append(f"DEFAULT {default_value}")
                else:
                    field_parts.append(f"DEFAULT '{default_value}'")
            elif isinstance(default_value, (int, float)):
                field_parts.append(f"DEFAULT {default_value}")
            elif isinstance(default_value, bool):
                field_parts.append(f"DEFAULT {str(default_value).upper()}")
        
        # Add enum constraints
        if field["type"] == "enum" and 'enum_values' in field:
            allowed_values = ', '.join([f"'{value}'" for value in field["enum_values"]])
            constraint_name = f"{field_name}_enum_check"
            field_parts.append(f"""CONSTRAINT "{constraint_name}" CHECK ("{field_name}" IN ({allowed_values}))""")
        
        return ' '.join(field_parts)
    
    def _generate_join_tables(self) -> List[str]:
        """
        Generate join tables for many-to-many relationships.
        
        Returns:
            List of SQL CREATE TABLE statements for join tables
        """
        join_tables = []
        
        for concept in self.concepts:
            # Handle new field-based relationships
            for field in concept["fields"]:
                if field["type"] == "relation_to_many":
                    target_concept_name = field["target"]
                    target_concept = self.concept_map.get(target_concept_name)
                    
                    if not target_concept:
                        continue
                        
                    # Check if target has a relation_to_one pointing back (which would make this 1:N)
                    is_one_to_many = False
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                             is_one_to_many = True
                             break
                    
                    if not is_one_to_many:
                        # It's Many-to-Many
                        table1 = concept["name"]
                        table2 = target_concept_name
                        join_table_name = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        # Only create the join table once
                        if join_table_name not in [jt.split('(')[0].strip() for jt in join_tables]:
                            sql = f"""
CREATE TABLE "{join_table_name}" (
  "{table1}_id" INTEGER NOT NULL,
  "{table2}_id" INTEGER NOT NULL,
  "_created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
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
            table_name = concept["name"]
            
            # Handle new field-based relationships
            for field in concept["fields"]:
                if field["type"] == "relation_to_one":
                    target_table = field["target"]
                    field_name = field["name"] # The column name is the field name
                    
                    constraint_name = f"fk_{table_name}_{field_name}"
                    
                    # Add constraint only (column already created in table definition)
                    fk_sql = f"""
ALTER TABLE "{table_name}"
  ADD CONSTRAINT "{constraint_name}"
  FOREIGN KEY ("{field_name}") REFERENCES "{target_table}"("id");"""
                    fk_constraints.append(fk_sql)


        
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
                

            
            visited.add(concept_name)
            sorted_concepts.append(concept)

        for concept in self.concepts:
            visit(concept["name"])
            
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
        table_name = concept["name"]
        data_size = concept["data_size"]
        num_records_by_data_size = lambda ds: 100 if ds == "m" else 10
        num_records = num_records_by_data_size(data_size)
        
        # Generate sample records
        sample_records = []
        
        for i in range(1, num_records + 1):
            field_values = []
            field_names = []
            
            for field in concept["fields"]:
                field_name = field["name"]
                field_type = field["type"]
                
                # Skip calculated fields or SERIAL fields as they are handled by the DB
                if 'calculated' in field or field["_be_sql_type"] == "SERIAL":
                    continue
                
                # Generate sample value based on type
                if field_type == "string":
                    if field_name == "email":
                        value = f"'{table_name}_{field_name}_{i}@example.com'"
                    else:
                        value = f"'{table_name}_{field_name}_{i}'"
                elif field_type == "integer":
                    value = str(i * 10)
                elif field_type == "decimal":
                    value = f"{i * 10}.{i:02d}"
                elif field_type == "boolean":
                    value = 'TRUE' if i % 2 == 0 else 'FALSE'
                elif field_type == "enum":
                    enum_values = field["enum_values"]
                    # Cycle through enum values
                    val_idx = (i - 1) % len(enum_values)
                    value = f"'{enum_values[val_idx]}'"
                elif field_type == "date":
                    # Cycle through days 1-28
                    day = ((i - 1) % 28) + 1
                    value = f"'2023-01-{day:02d}'"
                elif field_type == "datetime":
                    day = ((i - 1) % 28) + 1
                    value = f"'2023-01-{day:02d}T10:00:00Z'"
                elif field_type == "relation_to_one":
                    target_concept_name = field["target"]
                    if target_concept_name == concept["name"]:
                        # Recursive relationship (e.g., category.parent)
                        # Generic hierarchy: Level k has 2^(k+1) nodes.
                        # Each parent has 2 children.
                        if i <= 2:
                            value = "NULL"
                        else:
                            # Find level k such that i is in range [start_k, end_k]
                            # Level 0: 1-2
                            # Level 1: 3-6
                            # Level 2: 7-14
                            # ...
                            k = 1
                            while True:
                                level_start = 2 * (2**k - 1) + 1
                                level_end = 2 * (2**(k+1) - 1)
                                if level_start <= i <= level_end:
                                    prev_level_start = 2 * (2**(k-1) - 1) + 1
                                    parent_idx = (i - level_start) // 2 + prev_level_start
                                    value = str(parent_idx)
                                    break
                                k += 1
                                if k > 20: # Safety break
                                    value = "NULL"
                                    break
                    elif field.get("subtype") == "part_of":
                        # Triangular distribution: parent 1 gets 1, parent 2 gets 2, parent 3 gets 3...
                        # Find p such that sum(1..p-1) < i <= sum(1..p)
                        # sum(1..p) = p*(p+1)/2
                        p = 1
                        while (p * (p + 1)) // 2 < i:
                            p += 1
                        
                        # Check target count to avoid exceeding available parents
                        target_concept = self.concept_map.get(target_concept_name)
                        target_count = num_records_by_data_size(target_concept["data_size"]) if target_concept else 10
                        
                        parent_id = ((p - 1) % target_count) + 1
                        value = str(parent_id)
                    else:
                        # Check target concept data size to determine modulus
                        target_concept = self.concept_map.get(target_concept_name)
                        if target_concept:
                            target_size = target_concept["data_size"]
                            target_count = num_records_by_data_size(target_size)
                            # Distribute FKs across available target IDs (1 to target_count)
                            target_id = ((i - 1) % target_count) + 1
                            value = str(target_id)
                        else:
                             value = 'NULL'
                elif field_type == "relation_to_many":
                    continue
                else:
                    value = f"'{table_name}_{field_name}_{i}'"
                
                field_names.append(field_name)
                field_values.append(value)
            
            # Add timestamps
            field_names.extend(['_created_at', '_updated_at'])
            field_values.extend([f"'2023-01-01T10:00:00Z'", f"'2023-01-01T10:00:00Z'"])
            


            fields_str = ', '.join([f'"{field_name}"' for field_name in field_names])
            values_str = ', '.join(field_values)
            
            sample_records.append(f"({values_str})")
        
        if not sample_records:
            return ""
        
        return f'INSERT INTO "{table_name}" ({fields_str}) VALUES\n' + ",\n".join(sample_records) + ";"

    def _generate_presentation_triggers(self) -> List[str]:
        """
        Generate triggers for complex id_presentation fields.
        
        Returns:
            List of SQL statements for triggers
        """
        triggers = []
        
        for concept in self.concepts:
            presentation_config = concept["id_presentation"]
            if 'fields' not in presentation_config:
                continue
                
            presentation_fields = presentation_config["fields"]
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
            table_name = concept["name"]
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
                    
                    # Check fields for relation_to_one
                    for f in concept["fields"]:
                        if f["type"] == "relation_to_one" and f["name"] == rel_name:
                            rel = {
                                'type': 'belongs-to', 
                                'field_name': f["name"],
                                'target': f["target"]
                            }
                            break
                    

                    
                    if rel:
                        fk_col = rel.get("field_name", f"{rel["target"]}_id")
                        target_table = rel["target"]
                        declarations.append(f"{part_var} TEXT;")
                        
                        selects.append(f"""
    IF NEW."{fk_col}" IS NOT NULL THEN
        SELECT "{target_field}"::TEXT INTO {part_var} FROM "{target_table}" WHERE "id" = NEW."{fk_col}";
    END IF;"""
)
                        parts.append(f"COALESCE({part_var}, '')")
                    else:
                        parts.append("''")
                else:
                    # Local field
                    if field_name == "id":
                        parts.append(f"""COALESCE(NEW."id"::TEXT, '')""")
                    else:
                        field_exists = any(f["name"] == field_name for f in concept["fields"])
                        if field_exists:
                            parts.append(f"""COALESCE(NEW."{field_name}"::TEXT, '')""")
                        else:
                            parts.append("''")
            
            separator = presentation_config["separator"]
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
