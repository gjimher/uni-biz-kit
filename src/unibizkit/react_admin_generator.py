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
    ],
    "rules": {
      "no-unused-vars": "off"
    }
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
        
        # Check if ID should be shown
        presentation_config = concept.get('presentation_id')
        show_id = not presentation_config or 'fields' not in presentation_config
        
        # Check for owned children (ownership: true in child's belongs-to relationship)
        owned_children = self._find_owned_children(resource_name)
        
        # Generate field components based on field types
        field_components = self._generate_field_components(concept, owned_children)
        
        # Get optimized imports based on actual field types used
        react_admin_imports = self._get_optimized_react_admin_imports(concept, owned_children)
        
        # Determine MUI imports
        mui_imports = ["Grid"]
        if owned_children:
            mui_imports.extend(["Box", "Button", "Dialog", "DialogTitle", "DialogContent", "DialogActions"])
        mui_imports_str = ", ".join(mui_imports)
        
        # Generate Dialog Components for Children
        child_dialog_components = ""
        if owned_children:
            for child_info in owned_children:
                child_concept = child_info['concept']
                child_name = child_concept['name']
                fk_field_name = child_info['field_name']
                
                # Check if child ID should be shown
                child_presentation_config = child_concept.get('presentation_id')
                show_child_id = not child_presentation_config or 'fields' not in child_presentation_config
                
                # Generate create/edit fields for the child, excluding the foreign key to parent
                child_fields_res = self._generate_field_components(child_concept, exclude_fields=[fk_field_name])
                child_create_fields = child_fields_res['create_fields']
                child_edit_fields = child_fields_res['edit_fields']
                
                # Create Component Name
                create_comp_name = f"CREATE_{child_name.upper()}_FOR_{resource_name.upper()}"
                
                child_dialog_components += f"""
const {create_comp_name} = () => {{
  const {{ id }} = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  
  const handleClick = () => setOpen(true);
  const handleClose = () => setOpen(false);
  
  const onSuccess = () => {{
    notify('{child_name} created', {{ type: 'info', messageArgs: {{ smart_count: 1 }} }});
    setOpen(false);
    refresh();
  }};
  
  return (
    <>
      <Button onClick={{handleClick}} variant="contained" size="small">Add {child_name}</Button>
      <Dialog open={{open}} onClose={{handleClose}} fullWidth maxWidth="md">
        <DialogTitle>Create {child_name}</DialogTitle>
        <DialogContent>
          <Create resource="{child_name}" redirect={{false}} mutationOptions={{{{ onSuccess }}}} title=" ">
            <SimpleForm defaultValues={{{{ {fk_field_name}: id }}}}>
              <Grid container spacing={{2}}>
{child_create_fields}
              </Grid>
            </SimpleForm>
          </Create>
        </DialogContent>
      </Dialog>
    </>
  );
}};
"""
                # Edit Component Name
                edit_comp_name = f"EDIT_{child_name.upper()}_FOR_{resource_name.upper()}"
                
                child_id_field = ""
                if show_child_id:
                    child_id_field = f"""
                <Grid item xs={{12}} sm={{6}}>
                  <TextInput source="id" disabled fullWidth />
                </Grid>"""

                child_dialog_components += f"""
const {edit_comp_name} = () => {{
  const record = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const [update] = useUpdate();
  
  const handleClick = (e) => {{
    e.stopPropagation();
    setOpen(true);
  }};
  
  const handleClose = () => setOpen(false);
  
  const onSubmit = (data) => {{
    update(
      '{child_name}',
      {{ id: record.id, data: data, previousData: record }},
      {{
        onSuccess: () => {{
          notify('{child_name} updated', {{ type: 'info', messageArgs: {{ smart_count: 1 }} }});
          setOpen(false);
          refresh();
        }},
        onError: (error) => {{
          notify('Error: ' + error.message, {{ type: 'warning' }});
        }}
      }}
    );
  }};
  
  if (!record) return null;

  return (
    <>
      <Button onClick={{handleClick}} size="small" color="primary">Edit</Button>
      <Dialog open={{open}} onClose={{handleClose}} fullWidth maxWidth="md" onClick={{(e) => e.stopPropagation()}}>
        <DialogTitle>Edit {child_name}</DialogTitle>
        <DialogContent>
          <SimpleForm record={{record}} onSubmit={{onSubmit}}>
              <Grid container spacing={{2}}>{child_id_field}
{child_edit_fields}
              </Grid>
            </SimpleForm>
        </DialogContent>
      </Dialog>
    </>
  );
}};
"""

        # Prepare ID fields for main resource
        id_field_list = '<TextField source="id" />' if show_id else ''
        id_field_show = '<TextField source="id" />' if show_id else ''
        id_field_edit = """
          <Grid item xs={12} sm={6}>
            <TextInput source="id" disabled fullWidth />
          </Grid>""" if show_id else ""

        # Determine if we use SimpleForm or TabbedForm for Edit
        if owned_children:
            edit_component = f"""<Edit {{...props}}>
    <TabbedForm>
      <FormTab label="Summary">
        <Grid container spacing={{2}}>{id_field_edit}
          {field_components['edit_fields']}
        </Grid>
      </FormTab>
      {field_components['child_tabs']}
    </TabbedForm>
  </Edit>"""
        else:
            edit_component = f"""<Edit {{...props}}>
    <SimpleForm>
      <Grid container spacing={{2}}>{id_field_edit}
        {field_components['edit_fields']}
      </Grid>
    </SimpleForm>
  </Edit>"""

        resource_content = f"""import * as React from 'react';
import {{ {react_admin_imports} }} from 'react-admin';
import {{ {mui_imports_str} }} from '@mui/material';
{field_components['imports']}

{child_dialog_components}
export const {resource_name}_list = (props) => (
  <List {{...props}}>
    <Datagrid rowClick="edit">
      {id_field_list}
      {field_components['list_fields']}
    </Datagrid>
  </List>
);

export const {resource_name}_create = (props) => (
  <Create {{...props}}>
    <SimpleForm>
      <Grid container spacing={{2}}>
        {field_components['create_fields']}
      </Grid>
    </SimpleForm>
  </Create>
);

export const {resource_name}_edit = (props) => (
  {edit_component}
);

export const {resource_name}_show = (props) => (
  <Show {{...props}}>
    <SimpleShowLayout>
      {id_field_show}
      {field_components['show_fields']}
    </SimpleShowLayout>
  </Show>
);"""
        
        with open(resource_dir / f"{resource_name}.js", 'w', encoding='utf-8') as f:
            f.write(resource_content)
    
    def _find_owned_children(self, parent_concept_name: str) -> List[Dict[str, Any]]:
        """
        Find all concepts that have an ownership relationship with the parent concept.
        
        Args:
            parent_concept_name: Name of the parent concept
            
        Returns:
            List of dicts containing child concept info
        """
        children = []
        for concept in self.concepts:
            if 'relationships' in concept:
                for rel in concept['relationships']:
                    if rel['type'] == 'belongs-to' and rel.get('ownership') is True:
                         if rel['target'] == parent_concept_name:
                             # Found a child
                             field_name = rel.get('fieldName', f"{parent_concept_name}_id")
                             children.append({
                                 'concept': concept,
                                 'field_name': field_name,
                                 'rel': rel
                             })
        return children

    def _get_optimized_react_admin_imports(self, concept: Dict[str, Any], owned_children: List[Dict[str, Any]] = None) -> str:
        """
        Generate optimized React-Admin imports based on actual field types used.
        
        Args:
            concept: Concept definition
            owned_children: List of owned child concepts
            
        Returns:
            String of optimized imports
        """
        # Base components always needed
        needed_components = {
            'List', 'Create', 'Edit', 'Show',
            'SimpleShowLayout', 'SimpleForm', 'Datagrid',
            'TextField', 'TextInput', 'required'
        }
        
        # Add TabbedForm components if needed
        if owned_children:
            needed_components.add('TabbedForm')
            needed_components.add('FormTab')
            needed_components.add('ReferenceManyField')
            needed_components.add('useRecordContext')
            needed_components.add('useNotify')
            needed_components.add('useRefresh')
            needed_components.add('useUpdate')
            # CreateButton might not be needed if we use our own button, 
            # but we might use EditButton in the list
            needed_components.add('EditButton')
            
            for child in owned_children:
                 # Add child field types
                 for field in child['concept']['fields']:
                    ctype = self._map_field_type_to_component(field['type'])
                    if 'Number' in ctype: needed_components.add('NumberField')
                    if 'Date' in ctype: needed_components.add('DateField')
                    if 'Boolean' in ctype: needed_components.add('BooleanField')
                    
                    # Add imports needed for child form fields (like SelectInput for enums)
                    if field['type'] == 'enum': needed_components.add('SelectInput')
                    if field['type'] in ['integer', 'decimal']: needed_components.add('NumberInput')
                    if field['type'] == 'boolean': needed_components.add('BooleanInput')
                    if field['type'] in ['date', 'datetime']: needed_components.add('DateInput')
                 
                 # Check child relationships for ReferenceInput
                 if 'relationships' in child['concept']:
                     for rel in child['concept']['relationships']:
                         if rel['type'] == 'belongs-to':
                             needed_components.add('ReferenceInput')
                             needed_components.add('SelectInput')
                             needed_components.add('ReferenceField') # if displayed in list
        
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
        
        # Add id_presentation components if needed
        presentation_config = concept.get('presentation_id')
        if presentation_config and presentation_config.get('show', False):
            needed_components.add('TextField')
            needed_components.add('TextInput')
        
        # Add relationship components if needed
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] == 'belongs-to':
                    needed_components.add('ReferenceField')
                    needed_components.add('ReferenceInput')
                    needed_components.add('SelectInput')
                    break  # Only need to add once
        
        return ', '.join(sorted(needed_components))
    
    def _generate_field_components(self, concept: Dict[str, Any], owned_children: List[Dict[str, Any]] = None, exclude_fields: List[str] = None) -> Dict[str, str]:
        """
        Generate field components for a concept based on field types.
        
        Args:
            concept: Concept definition
            owned_children: List of owned child concepts (optional)
            exclude_fields: List of field names to exclude from inputs (optional)
            
        Returns:
            Dictionary with field components for different views
        """
        imports = []
        list_fields = []
        create_fields = []
        edit_fields = []
        show_fields = []
        child_tabs = []
        
        # Ensure exclude_fields is a list
        exclude_fields = exclude_fields or []
        
        # Add id_presentation if configured
        presentation_config = concept.get('presentation_id')
        if presentation_config and presentation_config.get('show', False):
            list_fields.append('      <TextField source="id_presentation" label="Presentation" />')
            show_fields.append('      <TextField source="id_presentation" label="Presentation" />')
            
            # Add to edit fields (read-only), but not create fields (it's generated)
            edit_fields.append('        <Grid item xs={12} sm={12}>')
            edit_fields.append('          <TextInput source="id_presentation" disabled fullWidth label="Presentation" />')
            edit_fields.append('        </Grid>')
        
        # Generate child tabs if any
        if owned_children:
            for child_info in owned_children:
                child_concept = child_info['concept']
                fk_field_name = child_info['field_name']
                child_name = child_concept['name']
                child_plural = child_concept.get('pluralName', f"{child_name}s")
                parent_name = concept['name']
                
                # Generate columns for the child list
                # Use presentation fields + id
                child_columns = []
                child_presentation_config = child_concept.get('presentation_id')
                if not child_presentation_config or 'fields' not in child_presentation_config:
                    child_columns.append(f'<TextField source="id" />')
                
                # Filter out the foreign key to parent (redundant in the list)
                relevant_fields = [f for f in child_concept['fields'] if f['name'] != fk_field_name]
                
                # Use a subset of fields for the list (first 4-5)
                count = 0
                for field in relevant_fields:
                    if count > 4: break
                    fname = field['name']
                    ftype = field['type']
                    
                    if ftype == 'string':
                        child_columns.append(f'<TextField source="{fname}" />')
                    elif ftype in ['integer', 'decimal']:
                        child_columns.append(f'<NumberField source="{fname}" />')
                    elif ftype == 'boolean':
                        child_columns.append(f'<BooleanField source="{fname}" />')
                    elif ftype in ['date', 'datetime']:
                        child_columns.append(f'<DateField source="{fname}" />')
                    elif ftype == 'enum':
                        child_columns.append(f'<TextField source="{fname}" />')
                    count += 1
                
                # Name of the custom component we generated in _generate_resource_main_file
                dialog_comp_name = f"CREATE_{child_name.upper()}_FOR_{parent_name.upper()}"
                edit_dialog_comp_name = f"EDIT_{child_name.upper()}_FOR_{parent_name.upper()}"
                
                child_columns.append(f"<{edit_dialog_comp_name} />")
                child_columns_str = '\n        '.join(child_columns)
                
                # Create the tab content
                tab_content = f"""
      <FormTab label="{child_plural}">
        <ReferenceManyField reference="{child_name}" target="{fk_field_name}" label={{false}}>
          <Box display="flex" justifyContent="flex-end" mb={{1}}>
            <{dialog_comp_name} />
          </Box>
          <Datagrid>
            {child_columns_str}
          </Datagrid>
        </ReferenceManyField>
      </FormTab>"""
                child_tabs.append(tab_content)

        
        for field in concept['fields']:
            field_name = field['name']
            field_type = field['type']
            is_required = field.get('required', False)
            field_size = field.get('size', 's')
            
            # Skip if field is in exclude_fields
            is_excluded = field_name in exclude_fields
            
            # Determine grid props
            if field_size in ['m', 'l']:
                grid_props = "xs={12} sm={12}"
            else:
                grid_props = "xs={12} sm={6}"
            
            # Generate appropriate field component based on type
            if field_type == 'string':
                list_fields.append(f"      <TextField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                
                # Setup input component props
                is_multiline = ' multiline' if field_size == 'l' else ''
                input_props = f"{is_multiline} fullWidth{validation}"
                
                if not is_excluded:
                    create_fields.append(f"        <Grid item {grid_props}>")
                    create_fields.append(f"          <TextInput source=\"{field_name}\"{input_props} />")
                    create_fields.append(f"        </Grid>")
                    
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(f"          <TextInput source=\"{field_name}\"{input_props} />")
                    edit_fields.append(f"        </Grid>")
                
                show_fields.append(f"      <TextField source=\"{field_name}\" />")
            
            elif field_type == 'integer':
                list_fields.append(f"      <NumberField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                
                if not is_excluded:
                    create_fields.append(f"        <Grid item {grid_props}>")
                    create_fields.append(f"          <NumberInput source=\"{field_name}\" fullWidth{validation} />")
                    create_fields.append(f"        </Grid>")
                    
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(f"          <NumberInput source=\"{field_name}\" fullWidth{validation} />")
                    edit_fields.append(f"        </Grid>")
                
                show_fields.append(f"      <NumberField source=\"{field_name}\" />")
            
            elif field_type == 'decimal':
                list_fields.append(f"      <NumberField source=\"{field_name}\" options={{{{ style: 'currency', currency: 'USD' }}}} />")
                validation = ' validate={[required()]}' if is_required else ''
                
                if not is_excluded:
                    create_fields.append(f"        <Grid item {grid_props}>")
                    create_fields.append(f"          <NumberInput source=\"{field_name}\" fullWidth{validation} />")
                    create_fields.append(f"        </Grid>")
                    
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(f"          <NumberInput source=\"{field_name}\" fullWidth{validation} />")
                    edit_fields.append(f"        </Grid>")
                
                show_fields.append(f"      <NumberField source=\"{field_name}\" options={{{{ style: 'currency', currency: 'USD' }}}} />")
            
            elif field_type == 'boolean':
                list_fields.append(f"      <BooleanField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                
                if not is_excluded:
                    create_fields.append(f"        <Grid item {grid_props}>")
                    create_fields.append(f"          <BooleanInput source=\"{field_name}\"{validation} />")
                    create_fields.append(f"        </Grid>")
                    
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(f"          <BooleanInput source=\"{field_name}\"{validation} />")
                    edit_fields.append(f"        </Grid>")
                
                show_fields.append(f"      <BooleanField source=\"{field_name}\" />")
            
            elif field_type == 'date':
                list_fields.append(f"      <DateField source=\"{field_name}\" />")
                validation = ' validate={[required()]}' if is_required else ''
                
                if not is_excluded:
                    create_fields.append(f"        <Grid item {grid_props}>")
                    create_fields.append(f"          <DateInput source=\"{field_name}\" fullWidth{validation} />")
                    create_fields.append(f"        </Grid>")
                    
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(f"          <DateInput source=\"{field_name}\" fullWidth{validation} />")
                    edit_fields.append(f"        </Grid>")
                
                show_fields.append(f"      <DateField source=\"{field_name}\" />")
            
            elif field_type == 'datetime':
                list_fields.append(f"      <DateField source=\"{field_name}\" showTime />")
                validation = ' validate={[required()]}' if is_required else ''
                
                if not is_excluded:
                    create_fields.append(f"        <Grid item {grid_props}>")
                    create_fields.append(f"          <DateInput source=\"{field_name}\" fullWidth{validation} />")
                    create_fields.append(f"        </Grid>")
                    
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(f"          <DateInput source=\"{field_name}\" fullWidth{validation} />")
                    edit_fields.append(f"        </Grid>")
                
                show_fields.append(f"      <DateField source=\"{field_name}\" showTime />")
            
            elif field_type == 'enum':
                enum_values = field.get('enumValues', [])
                if enum_values:
                    choices_str = ', '.join([f"{{ id: '{val}', name: '{val}' }}" for val in enum_values])
                    list_fields.append(f"      <TextField source=\"{field_name}\" />")
                    validation = ' validate={[required()]}' if is_required else ''
                    choices_array = f"[{choices_str}]"
                    
                    if not is_excluded:
                        create_fields.append(f"        <Grid item {grid_props}>")
                        create_fields.append("          <SelectInput source=\"" + field_name + "\" choices={" + choices_array + "}" + " fullWidth" + validation + " />")
                        create_fields.append(f"        </Grid>")
                        
                        edit_fields.append(f"        <Grid item {grid_props}>")
                        edit_fields.append("          <SelectInput source=\"" + field_name + "\" choices={" + choices_array + "}" + " fullWidth" + validation + " />")
                        edit_fields.append(f"        </Grid>")
                    
                    show_fields.append(f"      <TextField source=\"{field_name}\" />")
        
        # Add relationship fields
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] == 'belongs-to':
                    target_concept = relationship['target']
                    field_name = relationship.get('fieldName', f"{target_concept}_id")
                    
                    # Skip if relationship field is in exclude_fields
                    is_excluded = field_name in exclude_fields
                    
                    # Relationships usually 's' or 'm'. Default to 's' (half width)
                    grid_props = "xs={12} sm={6}"
                    
                    # Check if required
                    is_required = relationship.get('required', False)
                    validation = ' validate={[required()]}' if is_required else ''
                    
                    # Always use id_presentation for display in relationship fields
                    list_fields.append(f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept}\">")
                    list_fields.append(f"        <TextField source=\"id_presentation\" />")
                    list_fields.append(f"      </ReferenceField>")
                    
                    if not is_excluded:
                        create_fields.append(f"        <Grid item {grid_props}>")
                        create_fields.append(f"          <ReferenceInput source=\"{field_name}\" reference=\"{target_concept}\">")
                        create_fields.append(f"            <SelectInput optionText=\"id_presentation\" fullWidth{validation} />")
                        create_fields.append(f"          </ReferenceInput>")
                        create_fields.append(f"        </Grid>")
                        
                        edit_fields.append(f"        <Grid item {grid_props}>")
                        edit_fields.append(f"          <ReferenceInput source=\"{field_name}\" reference=\"{target_concept}\">")
                        edit_fields.append(f"            <SelectInput optionText=\"id_presentation\" fullWidth{validation} />")
                        edit_fields.append(f"          </ReferenceInput>")
                        edit_fields.append(f"        </Grid>")
                    
                    show_fields.append(f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept}\">")
                    show_fields.append(f"        <TextField source=\"id_presentation\" />")
                    show_fields.append(f"      </ReferenceField>")
        
        return {
            'imports': '\n'.join(imports),
            'list_fields': '\n'.join(list_fields),
            'create_fields': '\n'.join(create_fields),
            'edit_fields': '\n'.join(edit_fields),
            'show_fields': '\n'.join(show_fields),
            'child_tabs': '\n'.join(child_tabs)
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
