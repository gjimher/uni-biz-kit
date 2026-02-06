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
        
        # Clean src directory but preserve folders
        src_dir = self.output_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    (Path(root) / file).unlink()
        else:
            src_dir.mkdir()
        
        # Create subdirectories (ensure they exist)
        (src_dir / "resources").mkdir(exist_ok=True)
        (src_dir / "components").mkdir(exist_ok=True)
        (src_dir / "utils").mkdir(exist_ok=True)
        (src_dir / "layout").mkdir(exist_ok=True)
        
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
        """Generate data provider configuration with Many-to-Many support."""
        
        # Build Many-to-Many configuration map
        m2m_config = {}
        for concept in self.concepts:
            resource_name = concept['name']
            links = self._find_many_to_many_links(resource_name)
            if links:
                m2m_config[resource_name] = {}
                for link in links:
                    field_name = link.get('field_name')
                    m2m_config[resource_name][field_name] = {
                        'resource': link['join_table'],
                        'linkField': link['my_fk'],
                        'targetField': link['other_fk']
                    }
        
        import json
        m2m_config_json = json.dumps(m2m_config, indent=2)

        data_provider_content = f"""import {{ supabaseDataProvider }} from 'ra-supabase';
import {{ createClient }} from '@supabase/supabase-js';

// Use the correct Supabase URL format and ensure the key is properly configured
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_KEY;

const supabaseClient = createClient(supabaseUrl, supabaseKey);

const baseDataProvider = supabaseDataProvider({{
  instanceUrl: supabaseUrl,
  apiKey: supabaseKey,
  supabaseClient: supabaseClient
}});

const m2mConfig = {m2m_config_json};

export const dataProvider = {{
  ...baseDataProvider,
  
  getOne: async (resource, params) => {{
    const result = await baseDataProvider.getOne(resource, params);
    const config = m2mConfig[resource];
    
    if (config) {{
      await Promise.all(Object.keys(config).map(async (field) => {{
         const {{ resource: joinResource, linkField, targetField }} = config[field];
         const {{ data }} = await supabaseClient
             .from(joinResource)
             .select(`"${{targetField}}"`)
             .eq(`"${{linkField}}"`, result.data.id);
         
         if (data) {{
             result.data[field] = data.map(item => item[targetField]);
         }}
      }}));
    }}
    return result;
  }},

  create: async (resource, params) => {{
     const config = m2mConfig[resource];
     let m2mIds = {{}};
     
     if (config) {{
        Object.keys(config).forEach(field => {{
           if (params.data[field]) {{
               m2mIds[field] = params.data[field];
               delete params.data[field];
           }}
        }});
     }}
     
     const result = await baseDataProvider.create(resource, params);
     
     if (config && Object.keys(m2mIds).length > 0) {{
        const id = result.data.id;
        await Promise.all(Object.keys(m2mIds).map(async (field) => {{
            const {{ resource: joinResource, linkField, targetField }} = config[field];
            const ids = m2mIds[field];
            if (ids && ids.length > 0) {{
                const rows = ids.map(targetId => ({{
                    [linkField]: id,
                    [targetField]: targetId
                }}));
                await supabaseClient.from(joinResource).insert(rows);
            }}
        }}));
        Object.assign(result.data, m2mIds);
     }}
     return result;
  }},

  update: async (resource, params) => {{
     const config = m2mConfig[resource];
     let m2mIds = {{}};
     
     if (config) {{
        Object.keys(config).forEach(field => {{
           if (params.data[field] !== undefined) {{
               m2mIds[field] = params.data[field];
               delete params.data[field];
           }}
        }});
     }}
     
     const result = await baseDataProvider.update(resource, params);
     
     if (config && Object.keys(m2mIds).length > 0) {{
        const id = result.data.id;
        await Promise.all(Object.keys(m2mIds).map(async (field) => {{
            const {{ resource: joinResource, linkField, targetField }} = config[field];
            const newIds = m2mIds[field];
            
            // Delete existing links
            await supabaseClient.from(joinResource).delete().eq(`"${{linkField}}"`, id);
            
            // Insert new links
            if (newIds && newIds.length > 0) {{
                const rows = newIds.map(targetId => ({{
                    [linkField]: id,
                    [targetField]: targetId
                }}));
                await supabaseClient.from(joinResource).insert(rows);
            }}
        }}));
        Object.assign(result.data, m2mIds);
     }}
     return result;
  }}
}};"""
        
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
        
        # Check for many-to-many relationships
        many_to_many_links = self._find_many_to_many_links(resource_name)
        
        # Generate field components based on field types
        field_components = self._generate_field_components(concept, owned_children, many_to_many_links=many_to_many_links)
        
        # Get optimized imports based on actual field types used
        react_admin_imports = self._get_optimized_react_admin_imports(concept, owned_children, many_to_many_links)
        
        # Determine MUI imports
        mui_imports = ["Grid"]
        if owned_children or many_to_many_links:
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
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>
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
                  <TextInput source="id" disabled fullWidth size="small" margin="none" />
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
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>{child_id_field}
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
          <Grid item xs={12} sm={3}>
            <TextInput source="id" disabled fullWidth size="small" margin="none" />
          </Grid>""" if show_id else ""

        # Determine if we use SimpleForm or TabbedForm for Edit
        if owned_children or many_to_many_links:
            edit_component = f"""<Edit {{...props}}>
    <TabbedForm>
      <FormTab label="Summary">
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
          {field_components['edit_fields']}
        </Grid>
      </FormTab>
      {field_components['child_tabs']}
    </TabbedForm>
  </Edit>"""
        else:
            edit_component = f"""<Edit {{...props}}>
    <SimpleForm>
      <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
        {field_components['edit_fields']}
      </Grid>
    </SimpleForm>
  </Edit>"""

        resource_content = f"""import * as React from 'react';
import {{ {react_admin_imports} }} from 'react-admin';
import {{ {mui_imports_str} }} from '@mui/material';
{field_components['imports']}

{child_dialog_components}

const {resource_name}_filters = [
{field_components['filter_fields']}
];

export const {resource_name}_list = (props) => (
  <List {{...props}} filters={{{resource_name}_filters}}>
    <Datagrid rowClick="edit">
      {id_field_list}
      {field_components['list_fields']}
    </Datagrid>
  </List>
);

export const {resource_name}_create = (props) => (
  <Create {{...props}}>
    <SimpleForm>
      <Grid container rowSpacing={{0}} columnSpacing={{2}}>
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
            # Check fields for part_of relationship
            for field in concept['fields']:
                if field['type'] == 'relation_to_one' and field.get('subtype') == 'part_of':
                     if field['target'] == parent_concept_name:
                         children.append({
                             'concept': concept,
                             'field_name': field['name'],
                             'rel': field
                         })

            # Check legacy relationships
            if 'relationships' in concept:
                for rel in concept['relationships']:
                    if rel['type'] == 'belongs-to' and rel.get('ownership') is True:
                         if rel['target'] == parent_concept_name:
                             # Found a child
                             field_name = rel.get('field_name', f"{parent_concept_name}_id")
                             children.append({
                                 'concept': concept,
                                 'field_name': field_name,
                                 'rel': rel
                             })
        return children

    def _find_many_to_many_links(self, concept_name: str) -> List[Dict[str, Any]]:
        """
        Find all many-to-many relationships for a concept (both directions).
        
        Args:
            concept_name: Name of the concept
            
        Returns:
            List of dicts containing link info
        """
        links = []
        concept = self.concept_map.get(concept_name)
        if not concept:
            return links
            
        # 1. Links where concept is the source
        # Check fields
        for field in concept['fields']:
            if field['type'] == 'relation_to_many':
                target_name = field['target']
                target_concept = self.concept_map.get(target_name)
                if target_concept:
                    # Check if it's M:N or 1:N inverse
                    is_one_to_many = False
                    for target_field in target_concept['fields']:
                        if target_field['type'] == 'relation_to_one' and target_field['target'] == concept_name:
                             is_one_to_many = True
                             break
                    
                    if not is_one_to_many:
                        # M:N Join Table
                        table1 = concept_name
                        table2 = target_name
                        join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        links.append({
                            'target_concept': target_concept,
                            'join_table': join_table,
                            'my_fk': f"{concept_name}_id",
                            'other_fk': f"{target_name}_id",
                            'field_name': field['name'],
                            'rel': field
                        })

        if 'relationships' in concept:
            for rel in concept['relationships']:
                if rel['type'] == 'many-to-many':
                    target_name = rel['target']
                    target_concept = self.concept_map.get(target_name)
                    if target_concept:
                        # Join table name logic from supabase_generator: alphabetical order
                        table1 = concept_name
                        table2 = target_name
                        join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        links.append({
                            'target_concept': target_concept,
                            'join_table': join_table,
                            'my_fk': f"{concept_name}_id",
                            'other_fk': f"{target_name}_id",
                            'field_name': rel.get('field_name', f"{target_name}s"),
                            'rel': rel
                        })
                        
        # 2. Links where concept is the target
        for other_concept in self.concepts:
            other_name = other_concept['name']
            if other_name == concept_name:
                continue

            # Check fields
            for field in other_concept['fields']:
                if field['type'] == 'relation_to_many' and field['target'] == concept_name:
                     # Check if I have relation_to_one pointing back
                     is_one_to_many = False
                     for my_field in concept['fields']: 
                         if my_field['type'] == 'relation_to_one' and my_field['target'] == other_concept['name']:
                             is_one_to_many = True
                             break
                     
                     if not is_one_to_many:
                        # M:N Join Table
                        table1 = other_name
                        table2 = concept_name
                        join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        links.append({
                            'target_concept': other_concept,
                            'join_table': join_table,
                            'my_fk': f"{concept_name}_id",
                            'other_fk': f"{other_name}_id",
                            'field_name': other_concept.get('plural_name', f"{other_name}s"),
                            'rel': field
                        })
                
            if 'relationships' in other_concept:
                for rel in other_concept['relationships']:
                    if rel['type'] == 'many-to-many' and rel['target'] == concept_name:
                        # Join table name
                        table1 = other_name
                        table2 = concept_name
                        join_table = f"{min(table1, table2)}_{max(table1, table2)}"
                        
                        links.append({
                            'target_concept': other_concept,
                            'join_table': join_table,
                            'my_fk': f"{concept_name}_id",
                            'other_fk': f"{other_name}_id",
                            'field_name': other_concept.get('plural_name', f"{other_name}s"),
                            'rel': rel
                        })
        
        return links

    def _get_optimized_react_admin_imports(self, concept: Dict[str, Any], owned_children: List[Dict[str, Any]] = None, many_to_many_links: List[Dict[str, Any]] = None) -> str:
        """
        Generate optimized React-Admin imports based on actual field types used.
        
        Args:
            concept: Concept definition
            owned_children: List of owned child concepts
            many_to_many_links: List of m:n links
            
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
        if owned_children or many_to_many_links:
            needed_components.add('TabbedForm')
            needed_components.add('FormTab')
            needed_components.add('ReferenceManyField')
            needed_components.add('useRecordContext')
            needed_components.add('useNotify')
            needed_components.add('useRefresh')
            needed_components.add('useUpdate')
            needed_components.add('EditButton')
            
        if owned_children:
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
        
        if many_to_many_links:
            needed_components.add('ReferenceInput')
            needed_components.add('SelectInput')
            needed_components.add('ReferenceField')
            # For deleting links
            needed_components.add('DeleteButton')
            # For m:n input
            needed_components.add('ReferenceArrayInput')
            needed_components.add('SelectArrayInput')
            # For m:n display
            needed_components.add('ReferenceArrayField')
            needed_components.add('SingleFieldList')
            needed_components.add('ChipField')

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
            elif field_type == 'relation_to_one':
                needed_components.add('ReferenceField')
                needed_components.add('ReferenceInput')
                
                # Check target concept data size
                target_concept_name = field['target']
                target_concept = self.concept_map.get(target_concept_name)
                target_data_size = target_concept.get('data_size', 's') if target_concept else 's'
                
                if target_data_size != 's':
                    needed_components.add('AutocompleteInput')
                else:
                    needed_components.add('SelectInput')
            elif field_type == 'relation_to_many':
                # Check if it's M:N or 1:N
                target_name = field['target']
                target_concept = self.concept_map.get(target_name)
                is_one_to_many = False
                if target_concept:
                    for target_field in target_concept['fields']:
                        if target_field['type'] == 'relation_to_one' and target_field['target'] == concept['name']:
                             is_one_to_many = True
                             break
                
                if is_one_to_many:
                     needed_components.add('ReferenceManyField')
                     needed_components.add('Datagrid')
                     needed_components.add('TextField') # generic
                     needed_components.add('EditButton')
                else:
                     # M:N is handled by many_to_many_links logic, which adds imports below
                     pass
        
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
                    
                    # Check target concept data size
                    target_concept_name = relationship['target']
                    target_concept = self.concept_map.get(target_concept_name)
                    target_data_size = target_concept.get('data_size', 's') if target_concept else 's'
                    
                    if target_data_size != 's':
                        needed_components.add('AutocompleteInput')
                    else:
                        needed_components.add('SelectInput')
        
        return ', '.join(sorted(needed_components))
    
    def _generate_field_components(self, concept: Dict[str, Any], owned_children: List[Dict[str, Any]] = None, exclude_fields: List[str] = None, many_to_many_links: List[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Generate field components for a concept based on field types.
        
        Args:
            concept: Concept definition
            owned_children: List of owned child concepts (optional)
            exclude_fields: List of field names to exclude from inputs (optional)
            many_to_many_links: List of M:N links (optional)
            
        Returns:
            Dictionary with field components for different views
        """
        imports = []
        list_fields = []
        create_fields = []
        edit_fields = []
        show_fields = []
        child_tabs = []
        filter_fields = []
        
        # Ensure exclude_fields is a list
        exclude_fields = exclude_fields or []
        
        # Grid State Tracking
        # 12-column grid. Positions: 0, 3, 6, 9.
        create_grid_pos = 0
        
        # Determine initial edit_grid_pos based on ID visibility
        # Logic must match _generate_resource_main_file
        presentation_config = concept.get('presentation_id')
        show_id = not presentation_config or 'fields' not in presentation_config
        
        # If ID is shown, it takes sm=3, so we start at 3. Otherwise 0.
        edit_grid_pos = 3 if show_id else 0
        
        def update_grid(current_pos, width, fields_list):
            """
            Updates grid position and adds spacer if needed.
            Returns new position.
            """
            # Logic: If field is width 6 ('m') and we are at pos 3 (Col 2), 
            # we must skip to 6 (Col 3).
            if width == 6:
                if current_pos % 12 == 3:
                    # Insert spacer
                    fields_list.append('        <Grid item xs={12} sm={3} />')
                    current_pos += 3
            
            # Wrap logic is handled by MUI, but we track the 'virtual' cursor
            # If current_pos + width > 12, it wraps to next line
            if (current_pos % 12) + width > 12:
                # Effectively starts at 0 on next line
                current_pos = 0
                
            current_pos += width
            return current_pos

        # Add a "global" search if data_size is not 's'
        data_size = concept.get('data_size', 's')
        if data_size != 's':
            # Use id_presentation for "alwaysOn" search as it identifies the record
            filter_fields.append(f'  <TextInput label="Search" source="id_presentation@ilike" alwaysOn />')
        
        # Add id_presentation if configured
        if presentation_config and presentation_config.get('show', False):
            list_fields.append('      <TextField source="id_presentation" label="Presentation" />')
            show_fields.append('      <TextField source="id_presentation" label="Presentation" />')
            
            # Add to edit fields (read-only), but not create fields (it's generated)
            width_units = 3
            edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
            edit_fields.append(f'        <Grid item xs={{12}} sm={{{width_units}}}>')
            edit_fields.append('          <TextInput source="id_presentation" disabled fullWidth label="Presentation" margin="none" size="small" />')
            edit_fields.append('        </Grid>')
        
        # Generate child tabs if any
        if owned_children:
            for child_info in owned_children:
                child_concept = child_info['concept']
                fk_field_name = child_info['field_name']
                child_name = child_concept['name']
                child_plural = child_concept.get('plural_name', f"{child_name}s")
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
                    elif ftype == 'relation_to_one':
                        target_concept_name = field['target']
                        child_columns.append(f'<ReferenceField source="{fname}" reference="{target_concept_name}"><TextField source="id_presentation" /></ReferenceField>')
                    count += 1
                
                # Name of the custom component we generated in _generate_resource_main_file
                dialog_comp_name = f"CREATE_{child_name.upper()}_FOR_{parent_name.upper()}"
                edit_dialog_comp_name = f"EDIT_{child_name.upper()}_FOR_{parent_name.upper()}"
                
                child_columns.append(f"<{edit_dialog_comp_name} />")
                child_columns_str = '\n        '.join(child_columns)
                
                # Create the tab content
                tab_content = f"""
      <FormTab label="{child_plural}">
        <ReferenceManyField reference="{child_name}" target="&quot;{fk_field_name}&quot;" label={{false}}>
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
            
            # Determine if required
            is_required = field.get('required')
            if is_required is None:
                # Apply defaults
                if field_type == 'relation_to_one' and field.get('subtype') == 'part_of':
                    # If self-referencing (recursive), default to False
                    if field.get('target') == concept['name']:
                        is_required = False
                    else:
                        is_required = True
                else:
                    is_required = False

            field_size = field.get('size', 's')
            
            # Skip if field is in exclude_fields
            is_excluded = field_name in exclude_fields
            
            # Determine width units
            # s = 3, m = 6, l = 6
            width_units = 3
            if field_size in ['m', 'l']:
                width_units = 6
            
            grid_props = f"xs={{12}} sm={{{width_units}}}"
            
            # Generate appropriate field component based on type
            input_html = ""
            list_html = ""
            show_html = ""
            
            if field_type == 'string':
                list_html = f"      <TextField source=\"{field_name}\" />"
                validation = ' validate={[required()]}' if is_required else ''
                is_multiline = ' multiline rows={4}' if field_size == 'l' else ''
                input_props = f"{is_multiline} fullWidth{validation} margin=\"none\" size=\"small\""
                input_html = f"          <TextInput source=\"{field_name}\"{input_props} />"
                show_html = f"      <TextField source=\"{field_name}\" />"
            
            elif field_type == 'integer':
                list_html = f"      <NumberField source=\"{field_name}\" />"
                validation = ' validate={[required()]}' if is_required else ''
                input_html = f"          <NumberInput source=\"{field_name}\" fullWidth{validation} margin=\"none\" size=\"small\" />"
                show_html = f"      <NumberField source=\"{field_name}\" />"
            
            elif field_type == 'decimal':
                list_html = f"      <NumberField source=\"{field_name}\" options={{{{ style: 'currency', currency: 'USD' }}}} />"
                validation = ' validate={[required()]}' if is_required else ''
                input_html = f"          <NumberInput source=\"{field_name}\" fullWidth{validation} margin=\"none\" size=\"small\" />"
                show_html = f"      <NumberField source=\"{field_name}\" options={{{{ style: 'currency', currency: 'USD' }}}} />"
            
            elif field_type == 'boolean':
                list_html = f"      <BooleanField source=\"{field_name}\" />"
                validation = ' validate={[required()]}' if is_required else ''
                input_html = f"          <BooleanInput source=\"{field_name}\"{validation} margin=\"none\" size=\"small\" />"
                show_html = f"      <BooleanField source=\"{field_name}\" />"
            
            elif field_type == 'date':
                list_html = f"      <DateField source=\"{field_name}\" />"
                validation = ' validate={[required()]}' if is_required else ''
                input_html = f"          <DateInput source=\"{field_name}\" fullWidth{validation} margin=\"none\" size=\"small\" />"
                show_html = f"      <DateField source=\"{field_name}\" />"
            
            elif field_type == 'datetime':
                list_html = f"      <DateField source=\"{field_name}\" showTime />"
                validation = ' validate={[required()]}' if is_required else ''
                input_html = f"          <DateInput source=\"{field_name}\" fullWidth{validation} margin=\"none\" size=\"small\" />"
                show_html = f"      <DateField source=\"{field_name}\" showTime />"
            
            elif field_type == 'enum':
                enum_values = field.get('enum_values', [])
                if enum_values:
                    choices_str = ', '.join([f"{{ id: '{val}', name: '{val}' }}" for val in enum_values])
                    list_html = f"      <TextField source=\"{field_name}\" />"
                    validation = ' validate={[required()]}' if is_required else ''
                    choices_array = f"[{choices_str}]"
                    input_html = "          <SelectInput source=\"" + field_name + "\" choices={" + choices_array + "}" + " fullWidth" + validation + " margin=\"none\" size=\"small\" />"
                    if data_size != 's':
                        filter_fields.append(f"  <SelectInput source=\"{field_name}\" choices={{{choices_array}}} />")
                    show_html = f"      <TextField source=\"{field_name}\" />"

            elif field_type == 'relation_to_one':
                target_concept_name = field['target']
                
                validation = ' validate={[required()]}' if is_required else ''
                
                # Determine input type based on target concept data size
                target_concept = self.concept_map.get(target_concept_name)
                target_data_size = target_concept.get('data_size', 's') if target_concept else 's'
                
                if target_data_size != 's':
                    # Use AutocompleteInput for larger datasets
                    input_component = f'<AutocompleteInput optionText="id_presentation" filterToQuery={{searchText => ({{ "id_presentation@ilike": searchText }})}} fullWidth{validation} margin="none" size="small" />'
                    filter_component = f'<ReferenceInput source="{field_name}" reference="{target_concept_name}"><AutocompleteInput optionText="id_presentation" filterToQuery={{searchText => ({{ "id_presentation@ilike": searchText }})}} /></ReferenceInput>'
                else:
                    # Use SelectInput for small datasets
                    input_component = f'<SelectInput optionText="id_presentation" fullWidth{validation} margin="none" size="small" />'
                    filter_component = f'<ReferenceInput source="{field_name}" reference="{target_concept_name}"><SelectInput optionText="id_presentation" /></ReferenceInput>'

                # Always use id_presentation for display in relationship fields
                list_html = f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept_name}\"><TextField source=\"id_presentation\" /></ReferenceField>"
                
                input_html = f"          <ReferenceInput source=\"{field_name}\" reference=\"{target_concept_name}\">{input_component}</ReferenceInput>"
                
                if data_size != 's':
                    filter_fields.append(f"  {filter_component}")
                
                show_html = f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept_name}\"><TextField source=\"id_presentation\" /></ReferenceField>"

            elif field_type == 'relation_to_many':
                target_name = field['target']
                target_concept = self.concept_map.get(target_name)
                is_one_to_many = False
                if target_concept:
                    for target_field in target_concept['fields']:
                        if target_field['type'] == 'relation_to_one' and target_field['target'] == concept['name']:
                             is_one_to_many = True
                             break
                
                if is_one_to_many:
                     # 1:N Inverse
                     # Skip create/list for now (too complex for generic list)
                     
                     # Add to Edit/Show
                     # We need the target field name (foreign key) on the OTHER side
                     target_fk = f"{concept['name']}_id" # Default
                     # Find exact FK name
                     for target_field in target_concept['fields']:
                        if target_field['type'] == 'relation_to_one' and target_field['target'] == concept['name']:
                             target_fk = target_field['name']
                             break
                     
                     # Create a simple datagrid with id and presentation
                     # We reuse the logic from _generate_resource_main_file child tabs if possible, 
                     # but here we just drop a simple ReferenceManyField
                     
                     width_units = 3
                     if field_size in ['m', 'l']:
                         width_units = 6
                     # Manually add to edit_fields (bypassing the standard input_html adder which uses update_grid)
                     # But we must respect the grid flow.
                     
                     # Actually, to keep it simple, we treat it as a "large" input that takes full width
                     # But input_html is for Create too. ReferenceManyField fails in Create.
                     
                     # We'll set input_html to empty, and manually append to edit_fields/show_fields?
                     # The loop structure appends input_html to BOTH Create and Edit.
                     # We want Edit ONLY.
                     
                     # Let's use a trick: set input_html to empty.
                     # Append to edit_fields manually.
                     
                     ref_many = f"""        <Grid item xs={{12}} sm={{{width_units}}}>
          <ReferenceManyField reference="{target_name}" target="&quot;{target_fk}&quot;" label="{field['name']}">
            <Datagrid>
              <TextField source="id_presentation" />
              <EditButton />
            </Datagrid>
          </ReferenceManyField>
        </Grid>"""
                     edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
                     edit_fields.append(ref_many)
                     
                     show_html = f"""      <ReferenceManyField reference="{target_name}" target="&quot;{target_fk}&quot;" label="{field['name']}">
        <Datagrid>
          <TextField source="id_presentation" />
        </Datagrid>
      </ReferenceManyField>"""
                     
                else:
                     # M:N - Skip, handled by appended block
                     continue

            # Append to lists
            if list_html: list_fields.append(list_html)
            if show_html: show_fields.append(show_html)
            
            if input_html and not is_excluded:
                # Add to Create
                create_grid_pos = update_grid(create_grid_pos, width_units, create_fields)
                create_fields.append(f"        <Grid item {grid_props}>")
                create_fields.append(input_html)
                create_fields.append(f"        </Grid>")
                
                # Add to Edit
                edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
                edit_fields.append(f"        <Grid item {grid_props}>")
                edit_fields.append(input_html)
                edit_fields.append(f"        </Grid>")

        # Add relationship fields
        if 'relationships' in concept:
            for relationship in concept['relationships']:
                if relationship['type'] == 'belongs-to':
                    target_concept_name = relationship['target']
                    field_name = relationship.get('field_name', f"{target_concept_name}_id")
                    
                    # Skip if relationship field is in exclude_fields
                    is_excluded = field_name in exclude_fields
                    
                    rel_size = relationship.get('size', 's')
                    width_units = 3
                    if rel_size in ['m', 'l']:
                        width_units = 6
                    
                    grid_props = f"xs={{12}} sm={{{width_units}}}"
                    
                    # Check if required
                    is_required = relationship.get('required', False)
                    validation = ' validate={[required()]}' if is_required else ''
                    
                    # Determine input type based on target concept data size
                    target_concept = self.concept_map.get(target_concept_name)
                    target_data_size = target_concept.get('data_size', 's') if target_concept else 's'
                    
                    if target_data_size != 's':
                        # Use AutocompleteInput for larger datasets
                        input_component = f'<AutocompleteInput optionText="id_presentation" filterToQuery={{searchText => ({{ "id_presentation@ilike": searchText }})}} fullWidth{validation} margin="none" size="small" />'
                        filter_component = f'<ReferenceInput source="{field_name}" reference="{target_concept_name}"><AutocompleteInput optionText="id_presentation" filterToQuery={{searchText => ({{ "id_presentation@ilike": searchText }})}} /></ReferenceInput>'
                    else:
                        # Use SelectInput for small datasets
                        input_component = f'<SelectInput optionText="id_presentation" fullWidth{validation} margin="none" size="small" />'
                        filter_component = f'<ReferenceInput source="{field_name}" reference="{target_concept_name}"><SelectInput optionText="id_presentation" /></ReferenceInput>'

                    # Always use id_presentation for display in relationship fields
                    list_fields.append(f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept_name}\">")
                    list_fields.append(f"        <TextField source=\"id_presentation\" />")
                    list_fields.append(f"      </ReferenceField>")
                    
                    if not is_excluded:
                        # Add to Create
                        create_grid_pos = update_grid(create_grid_pos, width_units, create_fields)
                        create_fields.append(f"        <Grid item {grid_props}>")
                        create_fields.append(f"          <ReferenceInput source=\"{field_name}\" reference=\"{target_concept_name}\">")
                        create_fields.append(f"            {input_component}")
                        create_fields.append(f"          </ReferenceInput>")
                        create_fields.append(f"        </Grid>")
                        
                        # Add to Edit
                        edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
                        edit_fields.append(f"        <Grid item {grid_props}>")
                        edit_fields.append(f"          <ReferenceInput source=\"{field_name}\" reference=\"{target_concept_name}\">")
                        edit_fields.append(f"            {input_component}")
                        edit_fields.append(f"          </ReferenceInput>")
                        edit_fields.append(f"        </Grid>")

                    if data_size != 's':
                        filter_fields.append(f"  {filter_component}")
                    
                    show_fields.append(f"      <ReferenceField source=\"{field_name}\" reference=\"{target_concept_name}\">")
                    show_fields.append(f"        <TextField source=\"id_presentation\" />")
                    show_fields.append(f"      </ReferenceField>")
        
        # Add Many-to-Many inputs to Create/Edit
        if many_to_many_links:
            for link_info in many_to_many_links:
                target_name = link_info['target_concept']['name']
                field_name = link_info.get('field_name', f"{target_name}s")
                rel = link_info.get('rel', {})
                
                rel_size = rel.get('size', 's')
                width_units = 3
                if rel_size in ['m', 'l']:
                    width_units = 6
                
                # Update grid positions
                create_grid_pos = update_grid(create_grid_pos, width_units, create_fields)
                edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
                
                input_block = f"""        <Grid item xs={{12}} sm={{{width_units}}}>
          <ReferenceArrayInput source="{field_name}" reference="{target_name}">
            <SelectArrayInput optionText="id_presentation" fullWidth margin="none" size="small" />
          </ReferenceArrayInput>
        </Grid>"""
                
                create_fields.append(input_block)
                edit_fields.append(input_block)
                
                show_block = f"""      <ReferenceArrayField source="{field_name}" reference="{target_name}">
        <SingleFieldList>
          <ChipField source="id_presentation" />
        </SingleFieldList>
      </ReferenceArrayField>"""
                show_fields.append(show_block)
        
        return {
            'imports': '\n'.join(imports),
            'list_fields': '\n'.join(list_fields),
            'create_fields': '\n'.join(create_fields),
            'edit_fields': '\n'.join(edit_fields),
            'show_fields': '\n'.join(show_fields),
            'child_tabs': '\n'.join(child_tabs),
            'filter_fields': '\n'.join(filter_fields)
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
