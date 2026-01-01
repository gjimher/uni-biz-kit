"""
React-Admin Frontend Generation Module

Generates React-Admin frontend code from business concept definitions.
"""

from typing import Dict, Any, List
from .schema_loader import SchemaLoader
import os
import logging
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
        
        # Create src directory structure
        src_dir = self.output_dir / "src"
        src_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        (src_dir / "resources").mkdir(exist_ok=True)
        (src_dir / "components").mkdir(exist_ok=True)
        (src_dir / "utils").mkdir(exist_ok=True)
        (src_dir / "layout").mkdir(exist_ok=True)
        
        # Create public directory
        (self.output_dir / "public").mkdir(exist_ok=True)
    
    def _generate_package_json(self):
        """Generate package.json file."""
        package_json_content = """{
  "name": "unibizkit-react-admin",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@mui/material": "^5.15.0",
    "@mui/x-date-pickers": "^6.19.0",
    "react": "^18.2.0",
    "react-admin": "^4.16.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1",
    "ra-data-supabase": "^1.0.0"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject"
  },
  "eslintConfig": {
    "extends": [
      "react-app",
      "react-app/jest"
    ]
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
    
    def _generate_app_js(self):
        """Generate App.js file."""
        # Import statements for all resources
        import_statements = []
        resource_components = []
        
        for concept in self.concepts:
            resource_name = concept['name']
            import_statements.append(f"import {{ {resource_name}List, {resource_name}Create, {resource_name}Edit, {resource_name}Show }} from './resources/{resource_name}';")
            resource_components.append(f"    <Resource name=\"{resource_name.lower()}\" list={{ {resource_name}List }} create={{ {resource_name}Create }} edit={{ {resource_name}Edit }} show={{ {resource_name}Show }} />")
        
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
        data_provider_content = """import { supabaseDataProvider } from 'ra-data-supabase';

const supabaseClient = {
  url: process.env.REACT_APP_SUPABASE_URL,
  key: process.env.REACT_APP_SUPABASE_KEY,
};

export const dataProvider = supabaseDataProvider(supabaseClient);"""
        
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
        
        resource_content = f"""import * as React from 'react';
import {{ List, Create, Edit, Show, SimpleShowLayout, SimpleForm, TextField, DateField, BooleanField, NumberField, ReferenceField, ReferenceInput, SelectInput, TextInput, BooleanInput, NumberInput, DateInput, required, useRecordContext }} from 'react-admin';
{field_components['imports']}

export const {resource_name}List = (props) => (
  <List {{...props}}>
    <SimpleShowLayout>
      <TextField source="id" />
      {field_components['list_fields']}
    </SimpleShowLayout>
  </List>
);

export const {resource_name}Create = (props) => (
  <Create {{...props}}>
    <SimpleForm>
      {field_components['create_fields']}
    </SimpleForm>
  </Create>
);

export const {resource_name}Edit = (props) => (
  <Edit {{...props}}>
    <SimpleForm>
      <TextInput source="id" disabled />
      {field_components['edit_fields']}
    </SimpleForm>
  </Edit>
);

export const {resource_name}Show = (props) => (
  <Show {{...props}}>
    <SimpleShowLayout>
      <TextField source="id" />
      {field_components['show_fields']}
    </SimpleShowLayout>
  </Show>
);"""
        
        with open(resource_dir / f"{resource_name}.js", 'w', encoding='utf-8') as f:
            f.write(resource_content)
    
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
        
        # Add special imports for relationship fields
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] in ['belongs-to', 'many-to-many']:
                    target_concept = relationship['target']
                    imports.append(f"import {{ {target_concept}ReferenceField, {target_concept}ReferenceInput }} from '../resources/{target_concept}';")
        
        for field in concept['fields']:
            field_name = field['name']
            field_type = field['type']
            is_required = field.get('required', False)
            
            # Generate appropriate field component based on type
            if field_type == 'string':
                list_fields.append(f"      <TextField source=\"{field_name}\" />")
                create_fields.append(f"      <TextInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                edit_fields.append(f"      <TextInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                show_fields.append(f"      <TextField source=\"{field_name}\" />")
            
            elif field_type == 'integer':
                list_fields.append(f"      <NumberField source=\"{field_name}\" />")
                create_fields.append(f"      <NumberInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                edit_fields.append(f"      <NumberInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                show_fields.append(f"      <NumberField source=\"{field_name}\" />")
            
            elif field_type == 'decimal':
                list_fields.append(f"      <NumberField source=\"{field_name}\" options={{ style: 'currency', currency: 'USD' }} />")
                create_fields.append(f"      <NumberInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                edit_fields.append(f"      <NumberInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                show_fields.append(f"      <NumberField source=\"{field_name}\" options={{ style: 'currency', currency: 'USD' }} />")
            
            elif field_type == 'boolean':
                list_fields.append(f"      <BooleanField source=\"{field_name}\" />")
                create_fields.append(f"      <BooleanInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                edit_fields.append(f"      <BooleanInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                show_fields.append(f"      <BooleanField source=\"{field_name}\" />")
            
            elif field_type == 'date':
                imports.append("import { DateField, DateInput } from 'react-admin';")
                list_fields.append(f"      <DateField source=\"{field_name}\" />")
                create_fields.append(f"      <DateInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                edit_fields.append(f"      <DateInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                show_fields.append(f"      <DateField source=\"{field_name}\" />")
            
            elif field_type == 'datetime':
                imports.append("import { DateField, DateInput } from 'react-admin';")
                list_fields.append(f"      <DateField source=\"{field_name}\" showTime />")
                create_fields.append(f"      <DateInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                edit_fields.append(f"      <DateInput source=\"{field_name}\" {'validate={[required()]}' if is_required else ''} />")
                show_fields.append(f"      <DateField source=\"{field_name}\" showTime />")
            
            elif field_type == 'enum':
                enum_values = field.get('enumValues', [])
                if enum_values:
                    choices_str = ', '.join([f"['{val}', '{val}']" for val in enum_values])
                    list_fields.append(f"      <TextField source=\"{field_name}\" />")
                    create_fields.append(f"      <SelectInput source=\"{field_name}\" choices={{{choices_str}}} {'validate={[required()]}' if is_required else ''} />")
                    edit_fields.append(f"      <SelectInput source=\"{field_name}\" choices={{{choices_str}}} {'validate={[required()]}' if is_required else ''} />")
                    show_fields.append(f"      <TextField source=\"{field_name}\" />")
        
        # Add relationship fields
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] == 'belongs-to':
                    target_concept = relationship['target']
                    field_name = relationship.get('fieldName', f"{target_concept.lower()}_id")
                    
                    list_fields.append(f"      <{target_concept}ReferenceField source=\"{field_name}\" reference=\"{target_concept.lower()}\" />")
                    create_fields.append(f"      <{target_concept}ReferenceInput source=\"{field_name}\" reference=\"{target_concept.lower()}\" />")
                    edit_fields.append(f"      <{target_concept}ReferenceInput source=\"{field_name}\" reference=\"{target_concept.lower()}\" />")
                    show_fields.append(f"      <{target_concept}ReferenceField source=\"{field_name}\" reference=\"{target_concept.lower()}\" />")
        
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