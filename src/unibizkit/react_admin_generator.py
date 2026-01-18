"""
React-Admin Frontend Generation Module

Generates React-Admin frontend code from business concept definitions.
"""

from typing import Dict, Any, List
from .schema_loader import SchemaLoader
import os
import logging
import shutil
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)

class ReactAdminGenerator:
    def __init__(self, schema_loader: SchemaLoader, output_dir: str = "react-admin-app"):
        """
        Initialize the React-Admin generator.
        
        Args:
            schema_loader: SchemaLoader instance with loaded business schema
            output_dir: Directory where React-Admin app will be generated
        """
        self.schema_loader = schema_loader
        self.concepts = schema_loader.get_all_concepts()
        self.output_dir = Path(output_dir)
        self.concept_map = {concept['name']: concept for concept in self.concepts}
    
    def generate_frontend(self):
        """
        Generate complete React-Admin frontend.
        
        Creates the directory structure and all necessary files.
        """
        logger.info(f"Generating React-Admin frontend in {self.output_dir}")
        
        # Create directory structure
        self._create_directory_structure()
        
        # Generate main app files
        self._generate_package_json()
        self._generate_app_js()
        self._generate_index_js()
        
        # Generate data provider
        self._generate_data_provider()
        
        # Generate resources for each concept
        for concept in self.concepts:
            self._generate_resource_files(concept)
        
        logger.info("React-Admin frontend generation completed")
    
    def _create_directory_structure(self):
        """Create the directory structure for the React-Admin app."""
        # Create main directories
        self.output_dir.mkdir(exist_ok=True)
        
        # Remove and create src directory structure
        src_dir = self.output_dir / "src"
        if src_dir.exists():
          shutil.rmtree(src_dir)
        src_dir.mkdir()
        
        # Create subdirectories
        (src_dir / "resources").mkdir()
        (src_dir / "components").mkdir()
        (src_dir / "utils").mkdir()
        (src_dir / "layout").mkdir()
        
        # Create public directory
        (self.output_dir / "public").mkdir(exist_ok=True)
        
        # Generate index.html in public directory
        self._generate_index_html()
    
    def _generate_package_json(self):
        """Generate package.json file."""
        package_json_content = """{
  "name": "unibizkit-react-admin",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@mui/material": "^5.15.0",
    "@mui/x-date-pickers": "^6.19.0",
    "@supabase/supabase-js": "^2.89.0",
    "react": "^18.2.0",
    "react-admin": "^4.16.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1",
    "ra-supabase": "^3.5.2"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject",
    "lint": "eslint src/",
    "lint:fix": "eslint src/ --fix"
  },
  "eslintConfig": {
    "extends": [
      "react-app",
      "react-app/jest"
    ]
  },
  "devDependencies": {
    "eslint": "^8.57.0",
    "eslint-plugin-react": "^7.34.1"
  },
  "browserslist": {
    "production": [
      ">0.2%",
      "not dead",
      "not op_mini all"
    ],
    "development": [
      "last 1 chrome version",
      "last 1 firefox version",
      "last 1 safari version"
    ]
  }
}"""
        
        with open(self.output_dir / "package.json", 'w', encoding='utf-8') as f:
            f.write(package_json_content)
    
    def _generate_index_js(self):
        """Generate index.js file."""
        index_js_content = """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);"""
        
        with open(self.output_dir / "src" / "index.js", 'w', encoding='utf-8') as f:
            f.write(index_js_content)
    
    def _generate_index_html(self):
        """Generate index.html file in public directory."""
        index_html_content = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <title>UniBizKit React-Admin</title>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>"""
        
        with open(self.output_dir / "public" / "index.html", 'w', encoding='utf-8') as f:
            f.write(index_html_content)
    
    def _generate_app_js(self):
        """Generate App.js file."""
        # Import statements for all resources
        import_statements = []
        resource_components = []
        
        for concept in self.concepts:
            resource_name = concept['name']
            import_statements.append(f"import {{ {resource_name}_list, {resource_name}_create, {resource_name}_edit, {resource_name}_show }} from './resources/{resource_name}/{resource_name}.js';")
            resource_components.append(f"    <Resource name=\"{resource_name}\" list={{ {resource_name}_list }} create={{ {resource_name}_create }} edit={{ {resource_name}_edit }} show={{ {resource_name}_show }} />")
        
        app_js_content = f"""import * as React from 'react';
import {{ Admin, Resource }} from 'react-admin';
import {{ dataProvider }} from './dataProvider';
{chr(10).join(import_statements)}

const App = () => (
  <Admin dataProvider={{dataProvider}}>
{chr(10).join(resource_components)}
  </Admin>
);

export default App;"""
        
        with open(self.output_dir / "src" / "App.js", 'w', encoding='utf-8') as f:
            f.write(app_js_content)
    
    def _generate_data_provider(self):
        """Generate data provider configuration."""
        data_provider_content = """import { supabaseDataProvider } from 'ra-supabase';
import { createClient } from '@supabase/supabase-js';

// Use the correct Supabase URL format and ensure the key is properly configured
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_KEY;

const supabaseClient = createClient(supabaseUrl, supabaseKey);

// Create the data provider with the correct parameters
export const dataProvider = supabaseDataProvider({
  instanceUrl: supabaseUrl,
  apiKey: supabaseKey,
  supabaseClient: supabaseClient
});"""
        
        with open(self.output_dir / "src" / "dataProvider.js", 'w', encoding='utf-8') as f:
            f.write(data_provider_content)
    
    def _generate_resource_files(self, concept: Dict[str, Any]):
        """
        Generate all files for a single resource/concept.
        
        Args:
            concept: Concept definition
        """
        resource_name = concept['name']
        resource_dir = self.output_dir / "src" / "resources" / resource_name
        resource_dir.mkdir(exist_ok=True)
        
        # Generate the main resource file
        self._generate_resource_main_file(concept, resource_dir)
    
    def _generate_resource_main_file(self, concept: Dict[str, Any], resource_dir: Path):
        """
        Generate the main resource file with List, Create, Edit, and Show components.
        
        Args:
            concept: Concept definition
            resource_dir: Directory where resource files will be created
        """
        resource_name = concept['name']
        
        # Generate field components based on field types
        field_components = self._generate_field_components(concept)
        
        # Get optimized imports based on actual field types used
        react_admin_imports = self._get_optimized_react_admin_imports(concept)
        
        resource_content = f"""import * as React from 'react';
import {{ {react_admin_imports} }} from 'react-admin';
{field_components['imports']}

export const {resource_name}_list = (props) => (
  <List {{...props}}>
    <Datagrid>
      <TextField source="id" />
      {field_components['list_fields']}
    </Datagrid>
  </List>
);

export const {resource_name}_create = (props) => (
  <Create {{...props}}>
    <SimpleForm>
      {field_components['create_fields']}
    </SimpleForm>
  </Create>
);

export const {resource_name}_edit = (props) => (
  <Edit {{...props}}>
    <SimpleForm>
      <TextInput source="id" disabled />
      {field_components['edit_fields']}
    </SimpleForm>
  </Edit>
);

export const {resource_name}_show = (props) => (
  <Show {{...props}}>
    <SimpleShowLayout>
      <TextField source="id" />
      {field_components['show_fields']}
    </SimpleShowLayout>
  </Show>
);"""
        
        with open(resource_dir / f"{resource_name}.js", 'w', encoding='utf-8') as f:
            f.write(resource_content)
    
    def _get_optimized_react_admin_imports(self, concept: Dict[str, Any]) -> str:
        """
        Generate optimized React-Admin imports based on actual field types used.
        
        Args:
            concept: Concept definition
            
        Returns:
            String of optimized imports
        """
        # Base components always needed
        needed_components = {
            'List', 'Create', 'Edit', 'Show',
            'SimpleShowLayout', 'SimpleForm', 'Datagrid',
            'TextField', 'TextInput', 'required'
        }
        
        # Add components based on field types
        for field in concept['fields']:
            field_type = field['type']
            if field_type == 'date' or field_type == 'datetime':
                needed_components.add('DateField')
                needed_components.add('DateInput')
            elif field_type == 'boolean':
                needed_components.add('BooleanField')
                needed_components.add('BooleanInput')
            elif field_type == 'integer' or field_type == 'decimal':
                needed_components.add('NumberField')
                needed_components.add('NumberInput')
            elif field_type == 'enum':
                needed_components.add('SelectInput')
        
        # Add relationship components if needed
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] == 'belongs-to':
                    needed_components.add('ReferenceField')
                    needed_components.add('ReferenceInput')
                    break  # Only need to add once
        
        return ', '.join(sorted(needed_components))
    
    def _generate_field_components(self, concept: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate field components for a concept based on field types.
        
        Args:
            concept: Concept definition
            
        Returns:
            Dictionary with field components for different views
        """
        imports = []
        list_fields = []
        create_fields = []
        edit_fields = []
        show_fields = []
        
        # No need for special imports for relationship fields - we use standard react-admin components
        # if 'relationships' in concept:
        #     for relationship in concept['relationships']:
        #         if relationship['type'] in ['belongs-to', 'many-to-many']:
        #             target_concept = relationship['target']
        #             imports.append(f"import {{ {target_concept}ReferenceField, {target_concept}ReferenceInput }} from '../{target_concept}/{target_concept}.js';")
        
        for field in concept['fields']:
            field_name = field['name']
            field_type = field['type']
            is_required = field.get('required', False)
            
            # Generate appropriate field component based on type
            if field_type == 'string':
                list_fields.append(f"      <TextField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                create_fields.append(f"      <TextInput source=\"{field_name}\"{validation} />")
                edit_fields.append(f"      <TextInput source=\"{field_name}\"{validation} />")
                show_fields.append(f"      <TextField source=\"{field_name}\" />")
            
            elif field_type == 'integer':
                list_fields.append(f"      <NumberField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                create_fields.append(f"      <NumberInput source=\"{field_name}\"{validation} />")
                edit_fields.append(f"      <NumberInput source=\"{field_name}\"{validation} />")
                show_fields.append(f"      <NumberField source=\"{field_name}\" />")
            
            elif field_type == 'decimal':
                list_fields.append(f"      <NumberField source=\"{field_name}\" options={{{{ style: 'currency', currency: 'USD' }}}} />")
                validation = ' validate={[required()]}' if is_required else ''
                create_fields.append(f"      <NumberInput source=\"{field_name}\"{validation} />")
                edit_fields.append(f"      <NumberInput source=\"{field_name}\"{validation} />")
                show_fields.append(f"      <NumberField source=\"{field_name}\" options={{{{ style: 'currency', currency: 'USD' }}}} />")
            
            elif field_type == 'boolean':
                list_fields.append(f"      <BooleanField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                create_fields.append(f"      <BooleanInput source=\"{field_name}\"{validation} />")
                edit_fields.append(f"      <BooleanInput source=\"{field_name}\"{validation} />")
                show_fields.append(f"      <BooleanField source=\"{field_name}\" />")
            
            elif field_type == 'date':
                list_fields.append(f"      <DateField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                create_fields.append(f"      <DateInput source=\"{field_name}\"{validation} />")
                edit_fields.append(f"      <DateInput source=\"{field_name}\"{validation} />")
                show_fields.append(f"      <DateField source=\"{field_name}\" />")
            
            elif field_type == 'datetime':
                list_fields.append(f"      <DateField source=\"{field_name}\" showTime />")
                validation = ' validate={[required()]}' if is_required else ''
                create_fields.append(f"      <DateInput source=\"{field_name}\"{validation} />")
                edit_fields.append(f"      <DateInput source=\"{field_name}\"{validation} />")
                show_fields.append(f"      <DateField source=\"{field_name}\" showTime />")
            
            elif field_type == 'enum':
                enum_values = field.get('enumValues', [])
                if enum_values:
                    choices_str = ', '.join([f"{{ id: '{val}', name: '{val}' }}" for val in enum_values])
                    list_fields.append(f"      <TextField source=\"{field_name}\" />")
                    validation = ' validate={[required()]}' if is_required else ''
                    choices_array = f"[{choices_str}]"
                    create_fields.append("      <SelectInput source=\"" + field_name + "\" choices={" + choices_array + "}" + validation + " />")
                    edit_fields.append("      <SelectInput source=\"" + field_name + "\" choices={" + choices_array + "}" + validation + " />")
                    show_fields.append(f"      <TextField source=\"{field_name}\" />")
        
        # Add relationship fields
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] == 'belongs-to':
                    target_concept = relationship['target']
                    field_name = relationship.get('fieldName', f"{target_concept}_id")
                    
                    list_fields.append(f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept}\" />")
                    create_fields.append(f"      <ReferenceInput source=\"{field_name}\" reference=\"{target_concept}\" />")
                    edit_fields.append(f"      <ReferenceInput source=\"{field_name}\" reference=\"{target_concept}\" />")
                    show_fields.append(f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept}\" />")
        
        return {
            'imports': '\n'.join(imports),
            'list_fields': '\n'.join(list_fields),
            'create_fields': '\n'.join(create_fields),
            'edit_fields': '\n'.join(edit_fields),
            'show_fields': '\n'.join(show_fields)
        }
    
    def _map_field_type_to_component(self, field_type: str) -> str:
        """
        Map field types to appropriate React-Admin components.
        
        Args:
            field_type: Field type
            
        Returns:
            React-Admin component name
        """
        type_mapping = {
            'string': 'TextInput',
            'integer': 'NumberInput',
            'decimal': 'NumberInput',
            'boolean': 'BooleanInput',
            'date': 'DateInput',
            'datetime': 'DateInput',
            'enum': 'SelectInput'
        }
        
        return type_mapping.get(field_type, 'TextInput')
