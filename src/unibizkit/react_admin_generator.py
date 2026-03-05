"""
React-Admin Frontend Generation Module

Generates React-Admin frontend code from business concept definitions.
"""

from typing import Dict, Any, List
from .schema_loader import SchemaLoader
import os
import logging
import shutil
import copy
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
        self.concept_map = {concept["name"]: concept for concept in self.concepts}
        self.presentation_config = schema_loader.presentation_config
    
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
        
        # Generate Menu and Layout if configured
        has_custom_menu = self._generate_menu_component()
        if has_custom_menu:
            self._generate_layout_component()
            
        self._generate_index_js()
        
        # Generate data provider
        self._generate_data_provider()
        
        # Generate auth provider
        has_auth_provider = False
        if self.schema_loader.security_config.get("authentication_required"):
             self._generate_auth_provider()
             self._generate_login_page()
             has_auth_provider = True

        # Generate custom components
        self._generate_custom_components()
        
        # Generate resources for each concept
        for concept in self.concepts:
            self._generate_resource_files(concept)

        # Update App.js with AuthProvider if needed (Requires rewriting App.js generation call or moving it)
        # Actually, let's regenerate App.js with the correct props
        self._generate_app_js(has_custom_layout=has_custom_menu, has_auth_provider=has_auth_provider)
        
        logger.info("React-Admin frontend generation completed")

    def _generate_menu_component(self) -> bool:
        """
        Generate the custom Menu component.
        """
        menu_config = self.presentation_config.get("menu")
        
        if not menu_config:
            return False

        import json
        menu_items_json = json.dumps(menu_config, indent=2)
        
        menu_js_content = f"""import * as React from 'react';
import {{ Menu, useTranslate }} from 'react-admin';
import {{ Collapse, List, ListItemButton, ListItemIcon, ListItemText }} from '@mui/material';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import SubMenuIcon from '@mui/icons-material/ViewList';
import SecurityIcon from '@mui/icons-material/Security';
import UserIcon from '@mui/icons-material/People';
import RoleIcon from '@mui/icons-material/VerifiedUser';

const menuItems = {menu_items_json};

const SubMenu = ({{ handleToggle, isOpen, name, icon, children, dense }}) => {{
    const translate = useTranslate();
    const header = (
        <ListItemButton onClick={{handleToggle}} dense={{dense}}>
            <ListItemIcon sx={{{{ minWidth: 40 }}}}>
                {{icon}}
            </ListItemIcon>
            <ListItemText primary={{name}} />
            {{isOpen ? <ExpandLess /> : <ExpandMore />}}
        </ListItemButton>
    );

    return (
        <React.Fragment>
            {{header}}
            <Collapse in={{isOpen}} timeout="auto" unmountOnExit>
                <List
                    component="div"
                    disablePadding
                    sx={{{{
                        '& a': {{
                            paddingLeft: (theme) => theme.spacing(4),
                            transition: 'padding-left 195ms cubic-bezier(0.4, 0, 0.2, 1) 0ms',
                        }},
                    }}}}
                >
                    {{children}}
                </List>
            </Collapse>
        </React.Fragment>
    );
}};

const RenderMenu = ({{ items, state, handleToggle }}) => {{
  return items.map((item, index) => {{
     if (item.children) {{
         let Icon = SubMenuIcon;
         if (item.label === 'Security') Icon = SecurityIcon;

         return (
             <SubMenu 
                key={{item.label}} 
                name={{item.label}} 
                icon={{<Icon />}}
                isOpen={{state[item.label]}} 
                handleToggle={{() => handleToggle(item.label)}}
             >
                <RenderMenu items={{item.children}} state={{state}} handleToggle={{handleToggle}} />
             </SubMenu>
         );
     }} else {{
         let Icon = null;
         if (item.concept === 'user') Icon = <UserIcon />;
         if (item.concept === 'role') Icon = <RoleIcon />;

         return <Menu.Item key={{item.concept}} to={{`/${{item.concept}}`}} primaryText={{item.label}} leftIcon={{Icon}} />;
     }}
  }});
}};

export const MyMenu = () => {{
    const [state, setState] = React.useState({{}});
    const handleToggle = (menu) => {{
        setState(state => ({{ ...state, [menu]: !state[menu] }}));
    }};
    
    return (
        <Menu>
             <RenderMenu items={{menuItems}} state={{state}} handleToggle={{handleToggle}} />
        </Menu>
    );
}};
"""
        with open(self.output_dir / "src" / "layout" / "MyMenu.js", 'w', encoding='utf-8') as f:
            f.write(menu_js_content)
        return True

    def _generate_layout_component(self):
        """Generate the custom Layout component."""
        layout_js_content = """import * as React from 'react';
import { Layout } from 'react-admin';
import { MyMenu } from './MyMenu';

export const MyLayout = (props) => <Layout {...props} menu={MyMenu} />;
"""
        with open(self.output_dir / "src" / "layout" / "MyLayout.js", 'w', encoding='utf-8') as f:
            f.write(layout_js_content)
    
    def _generate_app_js(self, has_custom_layout: bool = False, has_auth_provider: bool = False):
        """Generate App.js file."""
        # Import statements for all resources
        import_statements = []
        resource_components = []
        
        for concept in self.concepts:
            resource_name = concept["name"]
            import_statements.append(f"import {{ {resource_name.upper()}_LIST, {resource_name.upper()}_CREATE, {resource_name.upper()}_EDIT, {resource_name.upper()}_SHOW }} from './resources/{resource_name}/{resource_name}.js';")
            resource_components.append(f"""          {{(permissions?.['{resource_name}']?.includes('read') || permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('read') || permissions?.['*']?.includes('write')) ? (
              <Resource name="{resource_name}" 
                  list={{ {resource_name.upper()}_LIST }} 
                  create={{(permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write')) ? {resource_name.upper()}_CREATE : null}} 
                  edit={{ {resource_name.upper()}_EDIT }} 
                  show={{ {resource_name.upper()}_SHOW }} 
              />
          ) : null}}""")
        
        layout_import = ""
        layout_prop = ""
        if has_custom_layout:
            layout_import = "import { MyLayout } from './layout/MyLayout';"
            layout_prop = " layout={MyLayout}"
            
        auth_import = ""
        auth_prop = ""
        require_auth = ""
        if has_auth_provider:
             auth_import = "import { authProvider } from './authProvider';\nimport { MyLoginPage } from './layout/MyLoginPage';"
             auth_prop = " authProvider={authProvider} loginPage={MyLoginPage}"
             require_auth = " requireAuth"
             
        app_js_content = f"""import * as React from 'react';
import {{ Admin, Resource }} from 'react-admin';
import {{ dataProvider }} from './dataProvider';
{layout_import}
{auth_import}
{chr(10).join(import_statements)}

const App = () => (
  <Admin{require_auth} dataProvider={{dataProvider}}{layout_prop}{auth_prop} mutationMode="pessimistic">
      {{permissions => (
          <>
{chr(10).join(resource_components)}
          </>
      )}}
  </Admin>
);

export default App;"""
        
        with open(self.output_dir / "src" / "App.js", 'w', encoding='utf-8') as f:
            f.write(app_js_content)

    def _generate_custom_components(self):
        """Generate custom reusable components."""
        title_js_content = """import * as React from 'react';
import { useRecordContext } from 'react-admin';

export const Title = ({ name }) => {
    const record = useRecordContext();
    return (
        <span>
            {name} {record ? `${record.id_presentation}` : ''}
        </span>
    );
};
"""
        with open(self.output_dir / "src" / "components" / "title.js", 'w', encoding='utf-8') as f:
            f.write(title_js_content)

        reorderable_datagrid_js = """import * as React from 'react';
import { 
    Datagrid, 
    DatagridBody, 
    RecordContextProvider, 
    useListContext, 
    useListSortContext,
    useUpdate, 
    useNotify, 
    useRefresh 
} from 'react-admin';
import { TableRow, TableCell } from '@mui/material';
import DragHandleIcon from '@mui/icons-material/Reorder';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';

const DragHandle = ({ disabled }) => (
    <TableCell padding="none">
        <DragHandleIcon 
            style={{ 
                cursor: disabled ? 'default' : 'grab', 
                color: disabled ? '#eee' : '#999', 
                marginLeft: '10px' 
            }} 
        />
    </TableCell>
);

const ReorderableDatagridRow = ({ record, id, index, isReorderable, children, ...rest }) => (
    <Draggable draggableId={String(id)} index={index} isDragDisabled={!isReorderable}>
        {(provided, snapshot) => (
            <TableRow
                ref={provided.innerRef}
                {...provided.draggableProps}
                {...(isReorderable ? provided.dragHandleProps : {})}
                style={{
                    ...provided.draggableProps.style,
                    backgroundColor: snapshot.isDragging ? '#eee' : 'white',
                    display: 'table-row',
                }}
                {...rest}
            >
                <DragHandle disabled={!isReorderable} />
                {React.Children.map(children, (field, i) => (
                    React.isValidElement(field) ? (
                        <RecordContextProvider value={record}>
                            <TableCell key={field.props.source || i}>
                                {field}
                            </TableCell>
                        </RecordContextProvider>
                    ) : null
                ))}
            </TableRow>
        )}
    </Draggable>
);

const ReorderableDatagridBody = ({ children, localData, isReorderable, ...rest }) => {
    const { isLoading } = useListContext();
    if (isLoading || !localData) return null;

    return (
        <Droppable droppableId="datagrid-body" isDropDisabled={!isReorderable}>
            {(provided) => (
                <tbody ref={provided.innerRef} {...provided.droppableProps} {...rest}>
                    {localData.map((record, index) => (
                        <ReorderableDatagridRow
                            key={record.id}
                            id={record.id}
                            index={index}
                            record={record}
                            isReorderable={isReorderable}
                        >
                            {children}
                        </ReorderableDatagridRow>
                    ))}
                    {provided.placeholder}
                </tbody>
            )}
        </Droppable>
    );
};

export const ReorderableDatagrid = ({ children, ...props }) => {
    const { data, resource, refetch, isLoading, sort } = useListContext();
    const { setSort } = useListSortContext();
    const [localData, setLocalData] = React.useState(data);
    const [update] = useUpdate();
    const notify = useNotify();

    const isReorderable = sort && sort.field === 'part_of_order';

    // Force ASC order for part_of_order to keep UI consistent
    React.useEffect(() => {
        if (sort && sort.field === 'part_of_order' && sort.order === 'DESC') {
            setSort({ field: 'part_of_order', order: 'ASC' });
        }
    }, [sort, setSort]);

    React.useEffect(() => {
        if (data) {
            if (isReorderable) {
                // Force sort by part_of_order to ensure UI consistency
                // This protects against the list context returning unsorted data
                const sortedData = [...data].sort((a, b) => {
                    const orderA = (a.part_of_order !== undefined && a.part_of_order !== null) ? a.part_of_order : Number.MAX_SAFE_INTEGER;
                    const orderB = (b.part_of_order !== undefined && b.part_of_order !== null) ? b.part_of_order : Number.MAX_SAFE_INTEGER;
                    return orderA - orderB;
                });
                setLocalData(sortedData);
            } else {
                setLocalData(data);
            }
        }
    }, [data, isReorderable]);

    if (isLoading || !localData) return null;

    const onDragEnd = async (result) => {
        if (!result.destination) return;
        if (result.destination.index === result.source.index) return;
        if (!isReorderable) return;

        const startIndex = result.source.index;
        const endIndex = result.destination.index;
        
        // 1. Calculate new order locally
        const reorderedData = Array.from(localData);
        const [removed] = reorderedData.splice(startIndex, 1);
        reorderedData.splice(endIndex, 0, removed);
        
        // 2. Map existing order values to the new positions
        const allOrders = localData
            .map((r, idx) => (r.part_of_order !== undefined && r.part_of_order !== null) ? r.part_of_order : idx)
            .sort((a, b) => a - b);
        
        const updates = [];
        const finalData = reorderedData.map((record, i) => {
            const targetOrder = allOrders[i];
            if (record.part_of_order !== targetOrder) {
                const updatedRecord = { ...record, part_of_order: targetOrder };
                updates.push(update(resource, {
                    id: record.id,
                    data: { part_of_order: targetOrder },
                    previousData: record
                }, { mutationMode: 'pessimistic' }));
                return updatedRecord;
            }
            return record;
        });

        // Update UI immediately
        setLocalData(finalData);

        try {
            if (updates.length > 0) {
                await Promise.all(updates);
                notify('Order updated', { type: 'info' });
            }
        } catch (error) {
            notify('Error updating order: ' + error.message, { type: 'warning' });
            setLocalData(data);
        }
    };


    return (
        <DragDropContext onDragEnd={onDragEnd}>
            <Datagrid {...props} body={<ReorderableDatagridBody localData={localData} isReorderable={isReorderable} />}>
                {children}
            </Datagrid>
        </DragDropContext>
    );
};
"""
        with open(self.output_dir / "src" / "components" / "reorderable_datagrid.js", 'w', encoding='utf-8') as f:
            f.write(reorderable_datagrid_js)

        recursive_parent_selector_js = """import * as React from 'react';
import { 
    ReferenceField, 
    TextField, 
    ReferenceInput, 
    AutocompleteInput,
    FormDataConsumer,
    useRecordContext
} from 'react-admin';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, Box, Typography } from '@mui/material';

export const RecursiveParentSelector = ({ source, reference, label, separator, displayField }) => {
    const [open, setOpen] = React.useState(false);
    const record = useRecordContext();
    
    // Filter out the current record to prevent self-referencing and cycles
    const filter = React.useMemo(() => {
        if (record && record.id) {
             // ra-data-postgrest expects 'field@op' syntax for custom operators
             const filters = { "id@neq": record.id };
             if (record[displayField]) {
                 filters["id_presentation@not.ilike"] = `%${separator}${record[displayField]}${separator}%`;
             }
             return filters;
        }
        return {};
    }, [record, separator, displayField]);

    return (
        <>
            <Box display="flex" alignItems="center" justifyContent="space-between" width="100%" sx={{ border: '1px solid #e0e0e0', borderRadius: 1, p: 1, minHeight: '56px', mb: 2 }}>
                <Box flexGrow={1}>
                    <Typography variant="caption" color="textSecondary" display="block">
                        {label}
                    </Typography>
                    <FormDataConsumer>
                        {({ formData }) => (
                             <ReferenceField source={source} reference={reference} record={formData} link={false}>
                                 <TextField source="id_presentation" />
                             </ReferenceField>
                        )}
                    </FormDataConsumer>
                </Box>
                <Button onClick={() => setOpen(true)} size="small" variant="outlined">Change</Button>
            </Box>
            <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
                <DialogTitle>Select {label}</DialogTitle>
                <DialogContent>
                    <Box pt={1}>
                        <ReferenceInput 
                            source={source} 
                            reference={reference} 
                            sort={{ field: 'id_presentation', order: 'ASC' }}
                            filter={filter}
                        >
                            <AutocompleteInput 
                                optionText="id_presentation" 
                                filterToQuery={searchText => ({ "id_presentation@ilike": searchText })}
                                fullWidth 
                                label={label}
                                onChange={() => setOpen(false)}
                            />
                        </ReferenceInput>
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>Close</Button>
                </DialogActions>
            </Dialog>
        </>
    );
};
"""
        with open(self.output_dir / "src" / "components" / "recursive_parent_selector.js", 'w', encoding='utf-8') as f:
            f.write(recursive_parent_selector_js)

        custom_edit_toolbar_js = """import * as React from 'react';
import { Toolbar, SaveButton, DeleteButton, usePermissions } from 'react-admin';

export const CustomEditToolbar = ({ resource, ...props }) => {
    const { permissions } = usePermissions();
    const canEdit = permissions?.[resource]?.includes('write') || permissions?.['*']?.includes('write');
    
    return (
        <Toolbar {...props}>
            <SaveButton disabled={!canEdit} />
            {canEdit && <DeleteButton mutationMode="pessimistic" />}
        </Toolbar>
    );
};
"""
        with open(self.output_dir / "src" / "components" / "custom_edit_toolbar.js", 'w', encoding='utf-8') as f:
            f.write(custom_edit_toolbar_js)

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
    "@mui/icons-material": "^5.15.0",
    "@mui/x-date-pickers": "^6.19.0",
    "@supabase/supabase-js": "^2.89.0",
    "react": "^18.2.0",
    "react-admin": "^4.16.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1",
    "ra-supabase": "^3.5.2",
    "@hello-pangea/dnd": "^16.5.0"
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
        locale = self.presentation_config["locale"]
        index_html_content = f"""<!DOCTYPE html>
<html lang="{locale}">
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
    

    def _generate_auth_provider(self):
        """Generate auth provider using explicit Supabase implementation."""
        import json
        rules_json = json.dumps(self.schema_loader.security_config["_acl"], indent=4)
        auth_provider_content = f"""import {{ createClient }} from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_KEY;
const supabaseClient = createClient(supabaseUrl, supabaseKey);

const RULES = {rules_json};

export const authProvider = {{
    login: async ({{ username, password }}) => {{
        // Supabase expects email, so we assume username is email or map it
        // Check if username looks like an email
        let email = username;
        if (!email.includes('@')) {{
            // Fallback for demo users (e.g. admin -> admin@test.com)
            email = `${{username}}@test.com`;
        }}

        const {{ data, error }} = await supabaseClient.auth.signInWithPassword({{
            email,
            password
        }});

        if (error) {{
            throw new Error(error.message);
        }}

        return data;
    }},
    logout: async () => {{
        await supabaseClient.auth.signOut();
        return Promise.resolve();
    }},
    checkError: async (error) => {{
        // If the error is 401 or 403, it's likely a permission/RLS issue from Supabase.
        // We do NOT want to log the user out (which happens if we return Promise.reject()),
        // we just want React-Admin to show a notification error.
        if (error.status === 401 || error.status === 403) {{
             return Promise.resolve();
        }}
        return Promise.resolve();
    }},
    checkAuth: async () => {{
        const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
        if (!session) {{
            return Promise.reject();
        }}
        return Promise.resolve();
    }},
    getPermissions: async () => {{
        const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
        if (!session) return Promise.resolve({{}});
        
        const roles = session.user?.app_metadata?.roles || [];
        const permissions = {{}};
        
        // RULES structure: concept -> {{ _main: {{ role: access }}, _fields: {{ field: {{ role: access }} }} }}
        for (const [concept, acl] of Object.entries(RULES)) {{
            const mainRules = acl._main || {{}};
            const fieldRules = acl._fields || {{}};
            
            for (const role of roles) {{
                // Concept level access
                const mainAccess = mainRules[role];
                if (mainAccess) {{
                    if (!permissions[concept]) permissions[concept] = [];
                    if (!permissions[concept].includes(mainAccess)) {{
                        permissions[concept].push(mainAccess);
                    }}
                }}
                
                // Field level access
                for (const [field, fRules] of Object.entries(fieldRules)) {{
                    const fieldAccess = fRules[role] || mainAccess; // Fallback to main if not explicitly set (though backend should pre-fill it)
                    if (fieldAccess) {{
                        const fieldKey = `${{concept}}.${{field}}`;
                        if (!permissions[fieldKey]) permissions[fieldKey] = [];
                        if (!permissions[fieldKey].includes(fieldAccess)) {{
                            permissions[fieldKey].push(fieldAccess);
                        }}
                    }}
                }}
            }}
        }}
        return Promise.resolve(permissions);
    }},
    getIdentity: async () => {{
        const {{ data: {{ user }} }} = await supabaseClient.auth.getUser();
        if (!user) return Promise.reject();
        return Promise.resolve({{ id: user.id, fullName: user.email }});
    }}
}};
"""
        with open(self.output_dir / "src" / "authProvider.js", 'w', encoding='utf-8') as f:
            f.write(auth_provider_content)

    def _generate_login_page(self):
        """Generate a custom login page to change labels."""
        login_page_content = """import * as React from 'react';
import { Login, LoginForm, TextInput } from 'react-admin';

const MyLoginForm = props => (
    <LoginForm {...props}>
        <TextInput
            source="username"
            label="Email"
            autoFocus
        />
    </LoginForm>
);

export const MyLoginPage = props => (
    <Login {...props}>
        <MyLoginForm />
    </Login>
);
"""
        with open(self.output_dir / "src" / "layout" / "MyLoginPage.js", 'w', encoding='utf-8') as f:
            f.write(login_page_content)

    def _generate_data_provider(self):
        """Generate data provider configuration with Many-to-Many support."""
        
        # Build Many-to-Many configuration map
        m2m_config = {}
        for concept in self.concepts:
            resource_name = concept["name"]
            links = self._find_many_to_many_links(resource_name)
            if links:
                m2m_config[resource_name] = {}
                for link in links:
                    field_name = link.get("field_name")
                    m2m_config[resource_name][field_name] = {
                        'resource': link["join_table"],
                        'linkField': link["my_fk"],
                        'targetField': link["other_fk"]
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
                            if (newIds && newIds.length > 0) {{                const rows = newIds.map(targetId => ({{
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
}};
"""
        
        with open(self.output_dir / "src" / "dataProvider.js", 'w', encoding='utf-8') as f:
            f.write(data_provider_content)
    
    def _generate_resource_files(self, concept: Dict[str, Any]):
        """
        Generate all files for a single resource/concept.
        
        Args:
            concept: Concept definition
        """
        resource_name = concept["name"]
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
        resource_name = concept["name"]
        
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
        
        # Generate Dialog Components for Children RECURSIVELY
        child_dialog_components_list = []
        visited_dialogs = set()
        if owned_children:
            for child_info in owned_children:
                # Generate dialogs for child (and its descendants)
                child_dialog_components_list.extend(self._generate_recursive_dialogs(child_info["concept"], resource_name, visited=visited_dialogs))
        
        child_dialog_components = "\n".join(child_dialog_components_list)

        # Re-evaluating: I'll import them separately to be safe.
        component_imports = [
            f"import {{ Title }} from '../../components/title';",
            f"import {{ CustomEditToolbar }} from '../../components/custom_edit_toolbar';"
        ]
        if "ReorderableDatagrid" in field_components["child_tabs"] or "ReorderableDatagrid" in child_dialog_components:
             component_imports.append(f"import {{ ReorderableDatagrid }} from '../../components/reorderable_datagrid';")
        if "RecursiveParentSelector" in field_components["create_fields"] or "RecursiveParentSelector" in field_components["edit_fields"]:
             component_imports.append(f"import {{ RecursiveParentSelector }} from '../../components/recursive_parent_selector';")
        component_imports_str = "\n".join(component_imports)

        # Prepare ID fields for main resource
        id_field_list = '<TextField source="id_presentation" label="Id" />'
        id_field_show = ""
        id_field_edit = ""

        # Determine if we use SimpleForm or TabbedForm for Edit
        relations_tab = ""
        if field_components.get("m2m_edit_fields"):
            relations_tab = f"""
      <FormTab label="Relations">
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{field_components["m2m_edit_fields"]}
        </Grid>
      </FormTab>"""

        if owned_children or many_to_many_links:
            edit_component = f"""<Edit title={{<Title name="{resource_name}" />}} {{...props}}>
    <TabbedForm toolbar={{<CustomEditToolbar resource="{resource_name}" />}}>
      <FormTab label="Summary">
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
          {field_components["edit_fields"]}
        </Grid>
      </FormTab>
      {field_components["child_tabs"]}
      {relations_tab}
    </TabbedForm>
  </Edit>"""
        else:
            edit_component = f"""<Edit title={{<Title name="{resource_name}" />}} {{...props}}>
    <SimpleForm toolbar={{<CustomEditToolbar resource="{resource_name}" />}}>
      <Grid container rowSpacing={{0}} columnSpacing={{2}}>{id_field_edit}
        {field_components["edit_fields"]}
      </Grid>
    </SimpleForm>
  </Edit>"""

        # Generate the main resource file with List, Create, Edit, and Show components.
        resource_name = concept["name"]

        resource_content = f"""import * as React from 'react';
import {{ {react_admin_imports} }} from 'react-admin';
import {{ {mui_imports_str} }} from '@mui/material';
{component_imports_str}
{field_components["imports"]}

{child_dialog_components}

const {resource_name}_filters = [
{field_components["filter_fields"]}
];

export const {resource_name.upper()}_LIST = (props) => {{
  const {{ permissions }} = usePermissions();
  return (
    <List {{...props}} filters={{{resource_name}_filters}}>
      <Datagrid rowClick="edit">
        {id_field_list}
        {field_components["list_fields"]}
      </Datagrid>
    </List>
  );
}};

export const {resource_name.upper()}_CREATE = (props) => {{
  const {{ permissions }} = usePermissions();
  return (
    <Create {{...props}}>
      <SimpleForm>
        <Grid container rowSpacing={{0}} columnSpacing={{2}}>
          {field_components["create_fields"]}
        </Grid>
      </SimpleForm>
    </Create>
  );
}};

export const {resource_name.upper()}_EDIT = (props) => {{
  const {{ permissions }} = usePermissions();
  return (
    {edit_component}
  );
}};

export const {resource_name.upper()}_SHOW = (props) => (
  <Show title={{<Title name="{resource_name}" />}} {{...props}}>
    <SimpleShowLayout>
      {id_field_show}
      {field_components["show_fields"]}
    </SimpleShowLayout>
  </Show>
);
"""
        
        with open(resource_dir / f"{resource_name}.js", 'w', encoding='utf-8') as f:
            f.write(resource_content)

    def _collect_all_descendants(self, concept_name: str, visited=None) -> List[Dict[str, Any]]:
        """
        Recursively find all descendant concepts (children, grandchildren, etc.).
        """
        if visited is None: visited = set()
        descendants = []
        children = self._find_owned_children(concept_name)
        for child in children:
            c_name = child["concept"]["name"]
            # Avoid self-references and already visited concepts to prevent infinite recursion
            if c_name not in visited:
                visited.add(c_name)
                descendants.append(child)
                descendants.extend(self._collect_all_descendants(c_name, visited))
        return descendants

    def _generate_recursive_dialogs(self, concept: Dict[str, Any], parent_name: str, visited=None) -> List[str]:
        """
        Recursively generate dialog components for a concept and its descendants.
        """
        if visited is None: visited = set()
        resource_name = concept["name"]
        
        # Avoid infinite recursion in self-referencing relationships or duplicate dialogs
        state_key = (resource_name, parent_name)
        if state_key in visited:
            return []
        visited.add(state_key)

        components = []
        
        # 1. Find children of this concept (Grandchildren of the root)
        my_children = self._find_owned_children(resource_name)
        
        # 2. Recursively generate dialogs for children first
        for child_info in my_children:
            # For self-referencing children, we only go one level deep for popups
            if child_info["concept"]["name"] == resource_name:
                continue
            components.extend(self._generate_recursive_dialogs(child_info["concept"], resource_name, visited))

        # 3. Generate CREATE and EDIT for current concept
        fk_field_name = ""
        for field in concept["fields"]:
            if field["type"] == "relation_to_one" and field["target"] == parent_name:
                fk_field_name = field["name"]
                break
        
        # Generate fields
        fields_res = self._generate_field_components(concept, owned_children=my_children, exclude_fields=[fk_field_name])
        
        create_fields = fields_res["create_fields"]
        edit_fields = fields_res["edit_fields"]
        child_tabs = fields_res["child_tabs"]
        
        # Component Names
        create_comp_name = f"CREATE_{resource_name.upper()}_FOR_{parent_name.upper()}"
        edit_comp_name = f"EDIT_{resource_name.upper()}_FOR_{parent_name.upper()}"
        
        # CREATE Component
        create_comp = f"""
const {create_comp_name} = () => {{
  const {{ id }} = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const {{ permissions }} = usePermissions();
  const canWrite = permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write');
  
  if (!canWrite) return null;

  const handleClick = () => setOpen(true);
  const handleClose = () => setOpen(false);
  
  const onSuccess = () => {{
    notify('{resource_name} created', {{ type: 'info', messageArgs: {{ smart_count: 1 }} }});
    setOpen(false);
    refresh();
  }};
  
  return (
    <>
      <Button onClick={{handleClick}} variant="contained" size="small">Add {resource_name}</Button>
      <Dialog open={{open}} onClose={{handleClose}} fullWidth maxWidth="md">
        <DialogTitle>Create {resource_name}</DialogTitle>
        <DialogContent>
          <Create resource="{resource_name}" redirect={{false}} mutationOptions={{{{ onSuccess }}}} title=" ">
            <SimpleForm defaultValues={{{{ {fk_field_name}: id }}}}>
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{create_fields}
              </Grid>
            </SimpleForm>
          </Create>
        </DialogContent>
      </Dialog>
    </>
  );
}};
"""
        components.append(create_comp)

        # EDIT Component
        # Determine if TabbedForm is needed
        form_content = ""
        if my_children:
             form_content = f"""<TabbedForm record={{record}} onSubmit={{onSubmit}} syncWithLocation={{false}} toolbar={{<EditToolbar />}}>
              <FormTab label="Summary">
                <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{edit_fields}
                </Grid>
              </FormTab>
{child_tabs}
            </TabbedForm>"""
        else:
             form_content = f"""<SimpleForm record={{record}} onSubmit={{onSubmit}} toolbar={{<EditToolbar />}}>
              <Grid container rowSpacing={{0}} columnSpacing={{2}}>
{edit_fields}
              </Grid>
            </SimpleForm>"""

        edit_comp = f"""
const {edit_comp_name} = () => {{
  const record = useRecordContext();
  const [open, setOpen] = React.useState(false);
  const notify = useNotify();
  const refresh = useRefresh();
  const [update] = useUpdate();
  const {{ permissions }} = usePermissions();
  const canWrite = permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write');
  
  const handleClick = (e) => {{
    e.stopPropagation();
    setOpen(true);
  }};
  
  const handleClose = () => setOpen(false);
  
  const onSubmit = (data) => {{
    update(
      '{resource_name}',
      {{ id: record.id, data: data, previousData: record }},
      {{
        onSuccess: () => {{
          notify('{resource_name} updated', {{ type: 'info', messageArgs: {{ smart_count: 1 }} }});
          setOpen(false);
          refresh();
        }},
        onError: (error) => {{
          notify('Error: ' + error.message, {{ type: 'warning' }});
        }},
        mutationMode: 'pessimistic'
      }}
    );
  }};

  const EditToolbar = props => (
    <Toolbar {{...props}}>
      <SaveButton disabled={{!canWrite}} />
      {{canWrite && <DeleteButton mutationMode="pessimistic" redirect={{false}} mutationOptions={{{{ onSuccess: () => {{ setOpen(false); refresh(); }} }}}} />}}
    </Toolbar>
  );
  
  if (!record) return null;

  return (
    <>
      <Button onClick={{handleClick}} size="small" color="primary">{{canWrite ? 'Edit' : 'Show'}}</Button>
      <Dialog open={{open}} onClose={{handleClose}} fullWidth maxWidth="md" onClick={{(e) => e.stopPropagation()}}>
        <DialogTitle><Title name="{resource_name}" /></DialogTitle>
        <DialogContent>
            {form_content}
        </DialogContent>
      </Dialog>
    </>
  );
}};
"""
        components.append(edit_comp)
        
        return components

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
            for field in concept["fields"]:
                if field["type"] == "relation_to_one" and field["subtype"] == "part_of":
                     if field["target"] == parent_concept_name:
                         children.append({
                             'concept': concept,
                             'field_name': field["name"],
                             'rel': field
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
        for field in concept["fields"]:
            if field["type"] == "relation_to_many":
                target_name = field["target"]
                target_concept = self.concept_map.get(target_name)
                if target_concept:
                    # Check if it's M:N or 1:N inverse
                    is_one_to_many = False
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept_name:
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
                            'field_name': field["name"],
                            'rel': field
                        })


                        
        # 2. Links where concept is the target
        for other_concept in self.concepts:
            other_name = other_concept["name"]
            if other_name == concept_name:
                continue

            # Check fields
            for field in other_concept["fields"]:
                if field["type"] == "relation_to_many" and field["target"] == concept_name:
                     # Check if I have relation_to_one pointing back
                     is_one_to_many = False
                     for my_field in concept["fields"]: 
                         if my_field["type"] == "relation_to_one" and my_field["target"] == other_concept["name"]:
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
                            'field_name': other_concept["plural_name"],
                            'rel': field
                        })
                

        
        return links

    def _get_optimized_react_admin_imports(self, concept: Dict[str, Any], owned_children: List[Dict[str, Any]] = None, many_to_many_links: List[Dict[str, Any]] = None) -> str:
        """
        Generate optimized React-Admin imports based on actual field types used.
        """
        # Base components
        needed_components = {
            'List', 'Create', 'Edit', 'Show',
            'SimpleShowLayout', 'SimpleForm', 'Datagrid',
            'TextField', 'TextInput', 'required', 'useRecordContext', 'usePermissions'
        }
        
        # Collect all recursive descendants to ensure their field types are imported
        all_descendants = []
        if owned_children:
             all_descendants = self._collect_all_descendants(concept["name"])
        
        # Add components for children tabs
        if all_descendants or many_to_many_links:
            needed_components.add('TabbedForm')
            needed_components.add('FormTab')
            needed_components.add('ReferenceManyField')
            needed_components.add('useRecordContext')
            needed_components.add('useNotify')
            needed_components.add('useRefresh')
            needed_components.add('useUpdate')
            needed_components.add('EditButton')
            needed_components.add('DeleteButton')
            needed_components.add('Toolbar')
            needed_components.add('SaveButton')
            
        if all_descendants:
            for child in all_descendants:
                 # Add child field types
                 for field in child["concept"]["fields"]:
                    # Use enriched component type
                    comp = field["_fe_component"]
                    list_comp = field["_fe_list_component"]
                    needed_components.add(comp)
                    needed_components.add(list_comp)
                 


        if many_to_many_links:
            needed_components.add('ReferenceInput')
            needed_components.add('SelectInput')
            needed_components.add('ReferenceField')
            needed_components.add('DeleteButton')
            needed_components.add('ReferenceArrayInput')
            needed_components.add('SelectArrayInput')
            needed_components.add('ReferenceArrayField')
            needed_components.add('SingleFieldList')
            needed_components.add('ChipField')

        # Add components based on field types
        for field in concept["fields"]:
            needed_components.add(field["_fe_component"])
            needed_components.add(field["_fe_list_component"])
            
            # Special imports for references
            if field["type"] == "relation_to_one":
                # Autocomplete vs Select was decided in enriched schema
                needed_components.add('ReferenceInput')
                needed_components.add('ReferenceField')
                needed_components.add('SelectInput') # Fallback/always useful?
                if field["_fe_component"] == "AutocompleteInput":
                     needed_components.add('AutocompleteInput')
            
            elif field["type"] == "relation_to_many":
                # Check if it's M:N or 1:N
                # ... Simplified: if it's 1:N inverse, we need:
                # needed_components.add('ReferenceManyField') # Already added by default mapping
                needed_components.add('EditButton')
        
        # Add id_presentation components
        presentation_config = concept["id_presentation"]
        if presentation_config["show"]:
            needed_components.add('TextField')
            needed_components.add('TextInput')
        
        return ', '.join(sorted(needed_components))
    
    def _generate_field_components(self, concept: Dict[str, Any], owned_children: List[Dict[str, Any]] = None, exclude_fields: List[str] = None, many_to_many_links: List[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Generate field components for a concept using enriched metadata.
        """
        imports = []
        list_fields = []
        create_fields = []
        edit_fields = []
        show_fields = []
        child_tabs = []
        filter_fields = []
        m2m_edit_fields = []
        
        exclude_fields = exclude_fields or []
        
        # Grid State Tracking
        create_grid_pos = 0
        edit_grid_pos = 0
        m2m_grid_pos = 0
        
        def update_grid(current_pos, width, fields_list):
            if width == 6:
                if current_pos % 12 == 3:
                    fields_list.append('        <Grid item xs={12} sm={3} />')
                    current_pos += 3
            if (current_pos % 12) + width > 12:
                current_pos = 0
            current_pos += width
            return current_pos

        # Add global search
        filter_fields.append(f'  <TextInput label="Search" source="id_presentation@ilike" alwaysOn />')
        
        # Generate child tabs
        if owned_children:
            for child_info in owned_children:
                child_concept = child_info["concept"]
                fk_field_name = child_info["field_name"]
                child_name = child_concept["name"]
                child_plural = child_concept["plural_name"]
                parent_name = concept["name"]
                
                child_columns = []
                child_columns.append(f'<TextField source="id_presentation" label="Id" />')
                
                relevant_fields = [f for f in child_concept["fields"] if f["name"] != fk_field_name and f["_fe_visibility"] != "internal"]
                count = 0
                for field in relevant_fields:
                    if count > 4: break
                    fname = field["name"]
                    # Use enriched list component
                    comp = field["_fe_list_component"]
                    
                    if field["type"] == "relation_to_one":
                        target = field["target"]
                        child_columns.append(f'<ReferenceField source="{fname}" reference="{target}"><TextField source="id_presentation" /></ReferenceField>')
                    elif field["type"] == "decimal" and field.get("subtype") == "money":
                         currency = self.presentation_config["currency"]
                         # Use specific currency locale, default is handled by schema validation
                         number_locale = self.presentation_config["number_locale"]
                         child_columns.append(f'<NumberField source="{fname}" options={{{{ style: "currency", currency: "{currency}" }}}} locales="{number_locale}" />')
                    else:
                         child_columns.append(f'<{comp} source="{fname}" />')
                    count += 1
                
                dialog_comp_name = f"CREATE_{child_name.upper()}_FOR_{parent_name.upper()}"
                edit_dialog_comp_name = f"EDIT_{child_name.upper()}_FOR_{parent_name.upper()}"
                
                child_columns.append(f"<{edit_dialog_comp_name} />")
                child_columns.append(f"{{(permissions?.['{child_name}']?.includes('write') || permissions?.['*']?.includes('write')) && <DeleteButton mutationMode='pessimistic' redirect={{false}} />}}")
                
                sort_prop = " sort={{ field: 'id_presentation', order: 'ASC' }}"
                datagrid_comp = "Datagrid"
                if any(f["name"] == "part_of_order" for f in child_concept["fields"]):
                    sort_prop = " sort={{ field: 'part_of_order', order: 'ASC' }}"
                    datagrid_comp = "ReorderableDatagrid"
                    # Add hidden field to ensure it is fetched
                    child_columns.append(f'<NumberField source="part_of_order" sx={{{{ display: "none" }}}} />')

                child_columns_str = '\n        '.join(child_columns)

                tab_content = f"""
      <FormTab label="{child_plural}">
        <ReferenceManyField reference="{child_name}" target="&quot;{fk_field_name}&quot;" label={{false}}{sort_prop}>
          <Box display="flex" justifyContent="flex-end" mb={{1}}>
            <{dialog_comp_name} />
          </Box>
          <{datagrid_comp}>
            {child_columns_str}
          </{datagrid_comp}>
        </ReferenceManyField>
      </FormTab>"""
                child_tabs.append(tab_content)
        
        # Process Fields
        for field in concept["fields"]:
            field_name = field["name"]
            
            # Enriched Metadata
            comp_type = field["_fe_component"]
            list_comp = field["_fe_list_component"]
            width_units = field["_fe_grid_width"]
            visibility = field["_fe_visibility"]
            is_required = field["_be_not_null"]
            
            # Skip if excluded
            if field_name in exclude_fields:
                continue

            grid_props = f"xs={{12}} sm={{{width_units}}}"
            
            # Common props
            validation = ' validate={[required()]}' if is_required else ''
            full_width = ' fullWidth'
            margin = ' margin="none" size="small"'
            
            disabled_prop = ""
            if visibility == "read_only":
                disabled_prop = " disabled"
            elif self.schema_loader.security_config.get("authentication_required"):
                disabled_prop = f" disabled={{!permissions?.['{concept['name']}.{field_name}']?.includes('write')}}"
            
            # Construct Input Component (Create/Edit)
            input_html = ""
            
            # Relation handling
            if field["type"] == "relation_to_one":
                target = field["target"]
                
                # Check for recursive relation
                if concept["_type"] == "recursive_part_of" and field.get("subtype") == "part_of":
                    # Recursive relation: Use RecursiveParentSelector
                    presentation = concept["id_presentation"]
                    separator = presentation["separator"]
                    
                    # Determine display field (last field in id_presentation that is not the parent ref)
                    pres_fields = presentation["fields"]
                    display_field = pres_fields[-1]

                    input_html = f'          <RecursiveParentSelector source="{field_name}" reference="{target}" label="{field_name}" separator="{separator}" displayField="{display_field}"{disabled_prop} />'
                    width_units = 6 # Force width 6 for recursive selector
                    grid_props = f"xs={{12}} sm={{{width_units}}}"
                    
                    # Filter field - keep standard input for filters
                    filter_inner = f'<SelectInput optionText="id_presentation" />'
                    filter_fields.append(f'  <ReferenceInput source="{field_name}" reference="{target}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{filter_inner}</ReferenceInput>')
                else:
                    # Standard relation
                    # Determine input based on data_size (handled by schema processor now!)
                    # processor set _fe_component correctly (e.g. AutocompleteInput)
                    # But we need to wrap it in ReferenceInput
                    
                    # Check specific input type from schema
                    input_inner = ""
                    if comp_type == "AutocompleteInput":
                         input_inner = f'<AutocompleteInput optionText="id_presentation" filterToQuery={{searchText => ({{ "id_presentation@ilike": searchText }})}}{full_width}{validation}{margin}{disabled_prop} />'
                    else:
                         input_inner = f'<SelectInput optionText="id_presentation"{full_width}{validation}{margin}{disabled_prop} />'
                    
                    input_html = f'          <ReferenceInput source="{field_name}" reference="{target}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{input_inner}</ReferenceInput>'
                    
                    # Filter field
                    filter_inner = input_inner.replace(f'{validation}{margin}{disabled_prop}', '')
                    filter_fields.append(f'  <ReferenceInput source="{field_name}" reference="{target}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>{filter_inner}</ReferenceInput>')

            elif field["type"] == "relation_to_many":
                # Similar logic as before for 1:N inverse vs M:N
                # ... (Logic for 1:N Inverse ReferenceManyField) ...
                target_name = field["target"]
                target_concept = self.concept_map.get(target_name)
                is_one_to_many = False
                if target_concept:
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                             is_one_to_many = True
                             break
                if is_one_to_many:
                     # 1:N Inverse - Add to Edit only?
                     # We handle it by appending to edit_fields manually below
                     pass
                else:
                    continue # M:N handled later

            elif field["type"] == "enum":
                enum_values = field["enum_values"]
                choices_str = ', '.join([f"{{ id: '{val}', name: '{val}' }}" for val in enum_values])
                choices_array = f"[{choices_str}]"
                input_html = f'          <SelectInput source="{field_name}" choices={{{choices_array}}}{full_width}{validation}{margin}{disabled_prop} />'
                filter_fields.append(f'  <SelectInput source="{field_name}" choices={{{choices_array}}} />')


            else:
                # Standard types
                extra_props = ""
                if field["size"] == "l":
                    extra_props = " multiline rows={4}"
                if field["type"] == "decimal":
                     # formatting?
                     pass
                
                input_html = f'          <{comp_type} source="{field_name}"{extra_props}{full_width}{validation}{margin}{disabled_prop} />'
                
                # Add filter for standard fields
                # We skip long text fields ('l') as filters
                if field["size"] != "l":
                    filter_fields.append(f'  <{comp_type} source="{field_name}" />')

            # Construct List Component
            list_html = ""
            if field["type"] == "relation_to_one":
                target = field["target"]
                list_html = f'      <ReferenceField source="{field_name}" reference="{target}"><TextField source="id_presentation" /></ReferenceField>'
            elif field["type"] == "relation_to_many":
                pass # Not in list
            elif field["type"] == "decimal":
                 if field.get("subtype") == "money":
                     currency = self.presentation_config["currency"]
                     
                     # Use specific currency locale for number formatting
                     # Default is handled by schema validation
                     number_locale = self.presentation_config["number_locale"]
                     
                     list_html = f"""      <NumberField source="{field_name}" options={{{{ style: 'currency', currency: '{currency}' }}}} locales="{number_locale}" />"""
                 else:
                     list_html = f'      <{list_comp} source="{field_name}" />'
            else:
                list_html = f'      <{list_comp} source="{field_name}" />'

            # Append to lists
            if list_html and visibility != "internal": list_fields.append(list_html)
            # Show uses same as list mostly
            if list_html and visibility != "internal": show_fields.append(list_html)

            # Add to Create/Edit
            # Check visibility
            if visibility != "internal":
                if input_html:
                    # CREATE
                    if visibility == "editable": # Read-only excluded from Create? Or shown disabled?
                        # Usually calculated/read-only not shown in create
                        create_grid_pos = update_grid(create_grid_pos, width_units, create_fields)
                        create_fields.append(f"        <Grid item {grid_props}>")
                        create_fields.append(input_html)
                        create_fields.append(f"        </Grid>")
                        
                        # Force new line for recursive parent selector
                        if concept["_type"] == "recursive_part_of" and field.get("subtype") == "part_of":
                             remaining = 12 - (create_grid_pos % 12)
                             if remaining < 12 and remaining > 0:
                                 create_fields.append(f'        <Grid item xs={{12}} sm={{{remaining}}} />')
                                 create_grid_pos += remaining
                    
                    # EDIT
                    edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
                    edit_fields.append(f"        <Grid item {grid_props}>")
                    edit_fields.append(input_html)
                    edit_fields.append(f"        </Grid>")
                    
                    # Force new line for recursive parent selector
                    if concept["_type"] == "recursive_part_of" and field.get("subtype") == "part_of":
                         remaining = 12 - (edit_grid_pos % 12)
                         if remaining < 12 and remaining > 0:
                             edit_fields.append(f'        <Grid item xs={{12}} sm={{{remaining}}} />')
                             edit_grid_pos += remaining

            # Handle 1:N Inverse explicitly if needed
            if field["type"] == "relation_to_many":
                # ... same logic as before to append ReferenceManyField to Edit ...
                target_name = field["target"]
                target_concept = self.concept_map.get(target_name)
                is_one_to_many = False
                if target_concept:
                    for target_field in target_concept["fields"]:
                        if target_field["type"] == "relation_to_one" and target_field["target"] == concept["name"]:
                             is_one_to_many = True
                             target_fk = target_field["name"]
                             break
                if is_one_to_many:
                     ref_many = f"""        <Grid item xs={{12}} sm={{{width_units}}}>
          <ReferenceManyField reference="{target_name}" target="&quot;{target_fk}&quot;" label="{field["name"]}">
            <Datagrid>
              <TextField source="id_presentation" />
              <EditButton />
            </Datagrid>
          </ReferenceManyField>
        </Grid>"""
                     edit_grid_pos = update_grid(edit_grid_pos, width_units, edit_fields)
                     edit_fields.append(ref_many)


        
        # Add Many-to-Many inputs to Create/Edit
        if many_to_many_links:
            for link_info in many_to_many_links:
                target_name = link_info["target_concept"]["name"]
                field_name = link_info.get("field_name", f"{target_name}s")
                rel = link_info.get("rel", {})
                
                rel_size = rel["size"]
                width_units = 3
                if rel_size in ['m', 'l']:
                    width_units = 6
                
                # Update grid positions
                m2m_grid_pos = update_grid(m2m_grid_pos, width_units, m2m_edit_fields)
                
                input_block = f"""        <Grid item xs={{12}} sm={{{width_units}}}>
          <ReferenceArrayInput source="{field_name}" reference="{target_name}" sort={{{{ field: "id_presentation", order: "ASC" }}}}>
            <SelectArrayInput optionText="id_presentation" fullWidth margin="none" size="small" />
          </ReferenceArrayInput>
        </Grid>"""
                
                m2m_edit_fields.append(input_block)
                
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
            'm2m_edit_fields': '\n'.join(m2m_edit_fields),
            'show_fields': '\n'.join(show_fields),
            'child_tabs': '\n'.join(child_tabs),
            'filter_fields': ',\n'.join(filter_fields)
        }
    
    def _map_field_type_to_component(self, field_type: str) -> str:
        # Kept for child component generation legacy fallback
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
