"""
Test React-Admin Generation

Tests for React-Admin frontend generation functionality.
"""

import pytest
import tempfile
import os
import shutil
from pathlib import Path
from unibizkit.schema_loader import SchemaLoader
from unibizkit.react_admin_generator import ReactAdminGenerator

class TestReactAdminGeneration:
    """Test cases for React-Admin generation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.schema_loader = SchemaLoader()
        ecommerce_path = Path(__file__).parent.parent / "examples" / "ecommerce_schema.json"
        self.schema_loader.load_and_validate(str(ecommerce_path))
        
        # Create temporary output directory
        self.temp_dir = tempfile.mkdtemp()
        self.generator = ReactAdminGenerator(self.schema_loader, self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_generate_frontend_creates_directory_structure(self):
        """Test that the frontend generation creates the correct directory structure."""
        self.generator.generate_frontend()
        
        # Check main directories
        assert os.path.exists(os.path.join(self.temp_dir, "src"))
        assert os.path.exists(os.path.join(self.temp_dir, "public"))
        
        # Check subdirectories
        assert os.path.exists(os.path.join(self.temp_dir, "src", "resources"))
        assert os.path.exists(os.path.join(self.temp_dir, "src", "components"))
        assert os.path.exists(os.path.join(self.temp_dir, "src", "utils"))
        assert os.path.exists(os.path.join(self.temp_dir, "src", "layout"))
    
    def test_generate_frontend_creates_main_files(self):
        """Test that the frontend generation creates main application files."""
        self.generator.generate_frontend()
        
        # Check main files
        assert os.path.exists(os.path.join(self.temp_dir, "package.json"))
        assert os.path.exists(os.path.join(self.temp_dir, "src", "index.js"))
        assert os.path.exists(os.path.join(self.temp_dir, "src", "App.js"))
        assert os.path.exists(os.path.join(self.temp_dir, "src", "dataProvider.js"))
        assert os.path.exists(os.path.join(self.temp_dir, "public", "index.html"))
    
    def test_generate_frontend_creates_resource_files(self):
        """Test that the frontend generation creates resource files for each concept."""
        self.generator.generate_frontend()
        
        concepts = self.schema_loader.get_all_concepts()
        
        for concept in concepts:
            resource_name = concept['name']
            resource_file = os.path.join(self.temp_dir, "src", "resources", resource_name, f"{resource_name}.js")
            assert os.path.exists(resource_file), f"Resource file not found: {resource_file}"
    
    def test_package_json_content(self):
        """Test that package.json has the correct content."""
        self.generator.generate_frontend()
        
        package_json_path = os.path.join(self.temp_dir, "package.json")
        with open(package_json_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check required dependencies
        assert '"react-admin"' in content
        assert '"ra-supabase"' in content
        assert '"@mui/material"' in content
        assert '"@supabase/supabase-js"' in content
        
        # Check scripts
        assert '"start"' in content
        assert '"build"' in content
    
    def test_app_js_content(self):
        """Test that App.js has the correct content."""
        self.generator.generate_frontend()
        
        app_js_path = os.path.join(self.temp_dir, "src", "App.js")
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check imports
        assert "import { Admin, Resource } from 'react-admin'" in content
        assert "import { dataProvider } from './dataProvider'" in content
        
        # Check that all concepts are imported
        concepts = self.schema_loader.get_all_concepts()
        for concept in concepts:
            resource_name = concept['name']
            assert f"import {{ {resource_name}List, {resource_name}Create, {resource_name}Edit, {resource_name}Show }}" in content
            assert f"from './resources/{resource_name}/{resource_name}.js'" in content
        
        # Check Admin component
        assert "<Admin dataProvider={dataProvider}>" in content
        
        # Check Resource components
        for concept in concepts:
            resource_name = concept['name']
            table_name = concept['name'].lower()
            assert f"<Resource name=\"{table_name}\"" in content
            assert f"list={{ {resource_name}List }}" in content
            assert f"create={{ {resource_name}Create }}" in content
            assert f"edit={{ {resource_name}Edit }}" in content
            assert f"show={{ {resource_name}Show }}" in content
    
    def test_data_provider_content(self):
        """Test that dataProvider.js has the correct content."""
        self.generator.generate_frontend()
        
        data_provider_path = os.path.join(self.temp_dir, "src", "dataProvider.js")
        with open(data_provider_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check Supabase data provider
        assert "supabaseDataProvider" in content
        assert "REACT_APP_SUPABASE_URL" in content
        assert "REACT_APP_SUPABASE_KEY" in content
    
    def test_product_resource_content(self):
        """Test that the Product resource file has the correct content."""
        self.generator.generate_frontend()
        
        product_resource_path = os.path.join(self.temp_dir, "src", "resources", "Product", "Product.js")
        with open(product_resource_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check component exports
        assert "export const ProductList" in content
        assert "export const ProductCreate" in content
        assert "export const ProductEdit" in content
        assert "export const ProductShow" in content
        
        # Check field components
        assert "TextField" in content
        assert "NumberField" in content
        assert "BooleanField" in content
        assert "TextInput" in content
        assert "NumberInput" in content
        assert "BooleanInput" in content
        
        # Check specific Product fields
        assert 'source="name"' in content
        assert 'source="price"' in content
        assert 'source="sku"' in content
        assert 'source="status"' in content
        assert 'source="isFeatured"' in content
    
    def test_customer_resource_content(self):
        """Test that the Customer resource file has the correct content."""
        self.generator.generate_frontend()
        
        customer_resource_path = os.path.join(self.temp_dir, "src", "resources", "Customer", "Customer.js")
        with open(customer_resource_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check component exports
        assert "export const CustomerList" in content
        assert "export const CustomerCreate" in content
        assert "export const CustomerEdit" in content
        assert "export const CustomerShow" in content
        
        # Check specific Customer fields
        assert 'source="firstName"' in content
        assert 'source="lastName"' in content
        assert 'source="email"' in content
        assert 'source="phone"' in content
        assert 'source="address"' in content
    
    def test_order_resource_relationships(self):
        """Test that the Order resource handles relationships correctly."""
        self.generator.generate_frontend()
        
        order_resource_path = os.path.join(self.temp_dir, "src", "resources", "CustomerOrder", "CustomerOrder.js")
        with open(order_resource_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that Customer relationship is handled with standard react-admin components
        assert "ReferenceField" in content
        assert "ReferenceInput" in content
        assert 'source="customer"' in content
        assert 'reference="customer"' in content
    
    def test_index_js_content(self):
        """Test that index.js has the correct content."""
        self.generator.generate_frontend()
        
        index_js_path = os.path.join(self.temp_dir, "src", "index.js")
        with open(index_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check React imports and rendering
        assert "import React from 'react'" in content
        assert "import ReactDOM from 'react-dom/client'" in content
        assert "import App from './App'" in content
        assert "ReactDOM.createRoot" in content
        assert "<React.StrictMode>" in content
        assert "<App />" in content
    
    def test_index_html_content(self):
        """Test that index.html has the correct content."""
        self.generator.generate_frontend()
        
        index_html_path = os.path.join(self.temp_dir, "public", "index.html")
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert "<!DOCTYPE html>" in content
        assert "<html lang=\"en\">" in content
        assert "<title>UniBizKit React-Admin</title>" in content
        assert '<div id="root"></div>' in content
    
    def test_enum_field_handling(self):
        """Test that enum fields are handled correctly."""
        self.generator.generate_frontend()
        
        product_resource_path = os.path.join(self.temp_dir, "src", "resources", "Product", "Product.js")
        with open(product_resource_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that enum fields use SelectInput
        assert "SelectInput" in content
        assert "choices=" in content
        assert "'draft'" in content
        assert "'published'" in content
        assert "'archived'" in content
    
    def test_required_field_validation(self):
        """Test that required fields have validation."""
        self.generator.generate_frontend()
        
        product_resource_path = os.path.join(self.temp_dir, "src", "resources", "Product", "Product.js")
        with open(product_resource_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that required fields have validate={[required()]}
        assert "validate={[required()]}" in content
        
        # Count should be appropriate for required fields
        # Product has several required fields: name, price, stockQuantity, sku, status
        required_count = content.count("validate={[required()]}")
        assert required_count >= 5