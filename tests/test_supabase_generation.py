"""
Test Supabase Schema Generation

Tests for Supabase database schema generation functionality.
"""

import pytest
from pathlib import Path
from unibizkit.schema_loader import SchemaLoader
from unibizkit.supabase_generator import SupabaseGenerator

class TestSupabaseGeneration:
    """Test cases for Supabase schema generation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.schema_loader = SchemaLoader()
        ecommerce_path = Path(__file__).parent.parent / "examples" / "ecommerce_schema.json"
        self.schema_loader.load_and_validate(str(ecommerce_path))
        self.generator = SupabaseGenerator(self.schema_loader)
    
    def test_generate_sql_schema_contains_tables(self):
        """Test that generated SQL contains tables for all concepts."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Check that all concept tables are created
        concepts = self.schema_loader.get_all_concepts()
        for concept in concepts:
            table_name = concept['name'].lower()
            assert f"CREATE TABLE {table_name}" in sql_schema
            assert f"{table_name} (" in sql_schema
    
    def test_generate_sql_schema_contains_primary_keys(self):
        """Test that generated SQL contains primary keys."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Check that each table has a primary key
        concepts = self.schema_loader.get_all_concepts()
        for concept in concepts:
            table_name = concept['name'].lower()
            assert f"id SERIAL PRIMARY KEY" in sql_schema
    
    def test_generate_sql_schema_contains_timestamps(self):
        """Test that generated SQL contains timestamp fields."""
        sql_schema = self.generator.generate_sql_schema()
        
        assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP" in sql_schema
        assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP" in sql_schema
    
    def test_generate_sql_schema_field_types(self):
        """Test that field types are correctly mapped to PostgreSQL types."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Test various field type mappings
        assert "TEXT" in sql_schema  # string fields
        assert "INTEGER" in sql_schema  # integer fields
        assert "DECIMAL" in sql_schema  # decimal fields
        assert "BOOLEAN" in sql_schema  # boolean fields
        assert "TIMESTAMP WITH TIME ZONE" in sql_schema  # datetime fields
    
    def test_generate_sql_schema_unique_constraints(self):
        """Test that unique constraints are generated."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Product SKU should be unique
        assert "CREATE UNIQUE INDEX product_sku_unique ON product (sku)" in sql_schema
        
        # Category name should be unique
        assert "CREATE UNIQUE INDEX category_name_unique ON category (name)" in sql_schema
    
    def test_generate_sql_schema_enum_constraints(self):
        """Test that enum constraints are generated."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Product status enum
        assert "status_enum_check" in sql_schema
        assert "CHECK (status IN ('draft', 'published', 'archived'))" in sql_schema
        
        # Order status enum
        assert "CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled'))" in sql_schema
    
    def test_generate_join_tables(self):
        """Test that join tables are generated for many-to-many relationships."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Category-Product many-to-many relationship should create a join table
        assert "CREATE TABLE category_product" in sql_schema
        assert "category_id INTEGER NOT NULL" in sql_schema
        assert "product_id INTEGER NOT NULL" in sql_schema
        assert "PRIMARY KEY (category_id, product_id)" in sql_schema
        assert "FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE CASCADE" in sql_schema
        assert "FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE" in sql_schema
    
    def test_generate_foreign_key_constraints(self):
        """Test that foreign key constraints are generated."""
        sql_schema = self.generator.generate_sql_schema()
        
        # CustomerOrder belongs-to Customer relationship
        assert "ALTER TABLE customerorder" in sql_schema
        assert "ADD COLUMN IF NOT EXISTS customer INTEGER" in sql_schema
        assert "ADD CONSTRAINT fk_customerorder_customer" in sql_schema
        assert "FOREIGN KEY (customer) REFERENCES customer(id)" in sql_schema
        
        # OrderItem belongs-to CustomerOrder relationship
        assert "ALTER TABLE orderitem" in sql_schema
        assert "ADD COLUMN IF NOT EXISTS CustomerOrder INTEGER" in sql_schema
        assert "ADD CONSTRAINT fk_orderitem_CustomerOrder" in sql_schema
        assert "FOREIGN KEY (CustomerOrder) REFERENCES customerorder(id)" in sql_schema
    
    def test_generate_sample_data(self):
        """Test that sample data is generated."""
        sample_data = self.generator.generate_sample_data_sql()
        
        # Check that INSERT statements are generated for each concept
        concepts = self.schema_loader.get_all_concepts()
        for concept in concepts:
            table_name = concept['name'].lower()
            assert f"INSERT INTO {table_name}" in sample_data
        
        # Check that multiple records are generated
        assert "VALUES" in sample_data
        assert "(" in sample_data and ")" in sample_data
    
    def test_product_table_structure(self):
        """Test the structure of the Product table."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Product table should have all expected fields
        product_fields = [
            "name TEXT NOT NULL",
            "description TEXT",
            "price DECIMAL(10, 2) NOT NULL",
            "stockQuantity INTEGER NOT NULL",
            "sku TEXT NOT NULL",
            "status TEXT NOT NULL",
            "isFeatured BOOLEAN",
            "createdAt TIMESTAMP WITH TIME ZONE",
            "updatedAt TIMESTAMP WITH TIME ZONE"
        ]
        
        for field in product_fields:
            assert field in sql_schema
    
    def test_customer_table_structure(self):
        """Test the structure of the Customer table."""
        sql_schema = self.generator.generate_sql_schema()
        
        # Customer table should have all expected fields
        customer_fields = [
            "firstName TEXT NOT NULL",
            "lastName TEXT NOT NULL",
            "email TEXT NOT NULL",
            "phone TEXT",
            "address TEXT",
            "createdAt TIMESTAMP WITH TIME ZONE"
        ]
        
        for field in customer_fields:
            assert field in sql_schema
        
        # Email should be unique
        assert "CREATE UNIQUE INDEX customer_email_unique ON customer (email)" in sql_schema