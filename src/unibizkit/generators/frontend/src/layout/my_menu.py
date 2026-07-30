import json
from ...context import Context

# JS snippets present only when the presentation customization system is
# generated (designer 'dev'/'production'); with 'off' the emitted menu matches
# the pre-customization output.

_CUSTOM_IMPORT = "import { useCustomization, DesignBadge } from '../components/customization';\n"

_CUSTOM_ICONS = """    Palette as CustomizationIcon,
    Brush as DesignerIcon,
"""

_VISIBILITY_HELPERS = """// An entry pointing at a resource the role cannot read would navigate to a
// route App.jsx never registered ("URL not found"), so it is not shown at all.
// The condition mirrors the resource registration there; a group disappears
// once every entry under it is hidden.
const canReadResource = (permissions, resource) => Boolean(
    permissions?.[resource]?.includes('read')
    || permissions?.[resource]?.includes('edit')
    || permissions?.[resource]?.includes('write')
    || permissions?.['*']?.includes('read')
    || permissions?.['*']?.includes('write')
);

const isMenuItemVisible = (item, permissions) => {
    if (item.children) return item.children.some((child) => isMenuItemVisible(child, permissions));
    if (item.workflow) return canReadResource(permissions, WORKFLOW_PAGE_ROUTES[item.workflow].slice(1));
    // The documentation pages describe the model, not its data: they are open to
    // every signed-in user (the same model already ships in the app bundle).
    if (item.docs) return true;
    return canReadResource(permissions, item.concept);
};"""

_RENDER_MENU_CUSTOM = """// Each entry carries its own design badge (targeting the item by path) and
// every level ends with a design-mode-only "Add entry" row — the menu edits
// stay WYSIWYG right in the sidebar.
const RenderMenu = ({ items, state, handleToggle, permissions, path = [] }) => {
  return items.map((item, index) => {
     // Hidden entries render as null instead of being filtered out of the
     // array: a design badge targets an item by its index in the model's menu,
     // so the indices must stay the same whatever the role can see.
     if (!isMenuItemVisible(item, permissions)) return null;
     const itemPath = path.concat(index);
     const badge = <DesignBadge target={{ kind: 'menuItem', path: itemPath, name: item.label }} />;
     if (item.children) {
         let Icon = SubMenuIcon;
         if (item.label === 'Security') Icon = SecurityIcon;
         if (item.children.length > 0 && item.children.every((child) => child.docs)) Icon = DocsIcon;

         return (
             <SubMenu
                key={item.label}
                name={item.label}
                icon={<Icon />}
                badge={badge}
                isOpen={state[item.label]}
                handleToggle={() => handleToggle(item.label)}
             >
                <RenderMenu items={item.children} state={state} handleToggle={handleToggle} permissions={permissions} path={itemPath} />
                <DesignBadge target={{ kind: 'menuAdd', path: itemPath }} />
             </SubMenu>
         );
     } else if (item.workflow) {
         const Icon = item.workflow === 'assignable_tasks' ? <AssignableTasksIcon /> : <MyTasksIcon />;
         return (
             <Menu.Item
                key={item.workflow}
                to={WORKFLOW_PAGE_ROUTES[item.workflow]}
                primaryText={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>{item.label}{badge}</span>}
                leftIcon={Icon}
             />
         );
     } else if (item.docs) {
         const { route, Icon } = DOCS_PAGES[item.docs];
         return (
             <Menu.Item
                key={`docs-${item.docs}`}
                to={route}
                primaryText={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>{item.label}{badge}</span>}
                leftIcon={<Icon />}
             />
         );
     } else {
         let Icon = null;
         if (item.concept === 'user') Icon = <UserIcon />;
         if (item.concept === 'role') Icon = <RoleIcon />;

         const desc = conceptDescriptions[item.concept];
         const label = (
           <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
             {item.label}
             {desc && (
               <Tooltip title={desc} placement="right">
                 <HelpOutlineIcon sx={{ fontSize: 14, cursor: 'help' }} />
               </Tooltip>
             )}
             {badge}
           </span>
         );
         return <Menu.Item key={item.concept} to={`/${item.concept}`} primaryText={label} leftIcon={Icon} />;
     }
  });
};"""

_RENDER_MENU_PLAIN = """const RenderMenu = ({ items, state, handleToggle, permissions }) => {
  return items.map((item, index) => {
     if (!isMenuItemVisible(item, permissions)) return null;
     if (item.children) {
         let Icon = SubMenuIcon;
         if (item.label === 'Security') Icon = SecurityIcon;
         if (item.children.length > 0 && item.children.every((child) => child.docs)) Icon = DocsIcon;

         return (
             <SubMenu
                key={item.label}
                name={item.label}
                icon={<Icon />}
                isOpen={state[item.label]}
                handleToggle={() => handleToggle(item.label)}
             >
                <RenderMenu items={item.children} state={state} handleToggle={handleToggle} permissions={permissions} />
             </SubMenu>
         );
     } else if (item.workflow) {
         const Icon = item.workflow === 'assignable_tasks' ? <AssignableTasksIcon /> : <MyTasksIcon />;
         return (
             <Menu.Item
                key={item.workflow}
                to={WORKFLOW_PAGE_ROUTES[item.workflow]}
                primaryText={item.label}
                leftIcon={Icon}
             />
         );
     } else if (item.docs) {
         const { route, Icon } = DOCS_PAGES[item.docs];
         return <Menu.Item key={`docs-${item.docs}`} to={route} primaryText={item.label} leftIcon={<Icon />} />;
     } else {
         let Icon = null;
         if (item.concept === 'user') Icon = <UserIcon />;
         if (item.concept === 'role') Icon = <RoleIcon />;

         const desc = conceptDescriptions[item.concept];
         const label = desc ? (
           <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
             {item.label}
             <Tooltip title={desc} placement="right">
               <HelpOutlineIcon sx={{ fontSize: 14, cursor: 'help' }} />
             </Tooltip>
           </span>
         ) : item.label;
         return <Menu.Item key={item.concept} to={`/${item.concept}`} primaryText={label} leftIcon={Icon} />;
     }
  });
};"""

_ITEMS_CUSTOM = """    const custom = useCustomization();
    const canReviewDesigns = designerAdminRole && (identity?.roles || []).includes(designerAdminRole);
    // Presentation customization overlays can replace the menu per role; the
    // generated menuItems stay as the fallback.
    const items = (custom && custom.menu) || menuItems;
"""

_CUSTOMIZATION_SUBMENU = """
             {canReviewDesigns && <SubMenu
                name="Customization"
                icon={<CustomizationIcon />}
                isOpen={state.Customization}
                handleToggle={() => handleToggle('Customization')}
             >
                <Menu.Item to="/_design" primaryText="Designer" leftIcon={<DesignerIcon />} />
             </SubMenu>}"""


def generate(ctx: Context) -> str:
    menu_items_json = json.dumps(ctx.presentation_config.get("menu"), indent=2)
    concept_descriptions = {c["name"]: c["description"] for c in ctx.concepts if c["description"]}
    concept_descriptions_json = json.dumps(concept_descriptions)
    integration_roles_json = json.dumps(ctx.integrations_config["roles"])
    has_integrations = str(bool(ctx.integrations_config["integrations"])).lower()
    version_resource = next((
        concept["name"] for concept in ctx.concepts
        if concept.get("_be_version_history")
    ), None)
    version_admin_role = (
        ctx.business_schema["versioning"].get("admin_role")
        if version_resource else None
    )
    designer_admin_role = (
        ctx.presentation_config.get("designer_admin_role")
        if ctx.presentation_config["designer"] == "production" else None
    )
    if ctx.customization:
        custom_import = _CUSTOM_IMPORT
        custom_icons = _CUSTOM_ICONS
        designer_admin_const = (
            "// Role that reviews per-user designer personalizations (designer 'production').\n"
            f"const designerAdminRole = {json.dumps(designer_admin_role)};\n"
        )
        submenu_badge_param = ", badge"
        submenu_badge_line = "            {badge}\n"
        render_menu = _RENDER_MENU_CUSTOM
        items_setup = _ITEMS_CUSTOM
        render_items = "items"
        root_add_badge = "\n             <DesignBadge target={{ kind: 'menuAdd', path: [] }} />"
        customization_submenu = _CUSTOMIZATION_SUBMENU
    else:
        custom_import = ""
        custom_icons = ""
        designer_admin_const = ""
        submenu_badge_param = ""
        submenu_badge_line = ""
        render_menu = _RENDER_MENU_PLAIN
        items_setup = ""
        render_items = "menuItems"
        root_add_badge = ""
        customization_submenu = ""
    return f"""import * as React from 'react';
import {{ Menu, useGetIdentity, usePermissions, useTranslate }} from 'react-admin';
{custom_import}import {{ Collapse, List, ListItemButton, ListItemIcon, ListItemText }} from '@mui/material';
import Tooltip from '@mui/material/Tooltip';
import {{
    ExpandLess,
    ExpandMore,
    ViewList as SubMenuIcon,
    Security as SecurityIcon,
    People as UserIcon,
    VerifiedUser as RoleIcon,
    HelpOutline as HelpOutlineIcon,
    Home as HomeIcon,
    AssignmentInd as AssignableTasksIcon,
    AssignmentTurnedIn as MyTasksIcon,
    Settings as OperationsIcon,
    Sync as IntegrationsIcon,
    History as VersionsIcon,
    Schema as ConceptsIcon,
    AccountTree as WorkflowsIcon,
    MenuBook as DocsIcon,
{custom_icons}}} from '@mui/icons-material';

// The built-in task pages are generated resources like any other; the menu
// keeps naming them by what they are, not by their internal concept name.
const WORKFLOW_PAGE_ROUTES = {{
    assignable_tasks: '/_assignable_task',
    my_tasks: '/_my_task',
}};

// Model documentation pages (see src/docs/): custom routes under /admin, not
// resources, so they carry their own icon here.
const DOCS_PAGES = {{
    roles: {{ route: '/_docs/roles', Icon: RoleIcon }},
    concepts: {{ route: '/_docs/concepts', Icon: ConceptsIcon }},
    workflows: {{ route: '/_docs/workflows', Icon: WorkflowsIcon }},
    security: {{ route: '/_docs/security', Icon: SecurityIcon }},
}};

const menuItems = {menu_items_json};
const conceptDescriptions = {concept_descriptions_json};
const integrationRoles = new Set({integration_roles_json});
const hasIntegrations = {has_integrations};
const versionResource = {json.dumps(version_resource)};
const versionAdminRole = {json.dumps(version_admin_role)};
{designer_admin_const}
{_VISIBILITY_HELPERS}

const SubMenu = ({{ handleToggle, isOpen, name, icon{submenu_badge_param}, children, dense }}) => {{
    const translate = useTranslate();
    const header = (
        <ListItemButton onClick={{handleToggle}} dense={{dense}}>
            <ListItemIcon sx={{{{ minWidth: 40 }}}}>
                {{icon}}
            </ListItemIcon>
            <ListItemText primary={{name}} />
{submenu_badge_line}            {{isOpen ? <ExpandLess /> : <ExpandMore />}}
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

{render_menu}

export const MyMenu = () => {{
    const {{ identity }} = useGetIdentity();
    // Until the permissions resolve nothing is shown, so no entry can flash and
    // then vanish once the role is known.
    const {{ permissions }} = usePermissions();
    const [state, setState] = React.useState({{}});
    const handleToggle = (menu) => {{
        setState(state => ({{ ...state, [menu]: !state[menu] }}));
    }};
    const canOperateIntegrations = hasIntegrations && (identity?.roles || []).some(role => integrationRoles.has(role));
    const canOperateVersions = versionAdminRole && (identity?.roles || []).includes(versionAdminRole);
{items_setup}
    return (
        <Menu>
            <ListItemButton component="a" href="#/" sx={{{{ pl: 2, py: 1 }}}}>
                <ListItemIcon sx={{{{ minWidth: 40 }}}}>
                    <HomeIcon />
                </ListItemIcon>
                <ListItemText primary="Home" />
            </ListItemButton>
             <RenderMenu items={{{render_items}}} state={{state}} handleToggle={{handleToggle}} permissions={{permissions}} />{root_add_badge}
             {{(canOperateIntegrations || canOperateVersions) && <SubMenu
                name="Operations"
                icon={{<OperationsIcon />}}
                isOpen={{state.Operations}}
                handleToggle={{() => handleToggle('Operations')}}
             >
                {{canOperateIntegrations && <Menu.Item to="/_integration" primaryText="Integrations" leftIcon={{<IntegrationsIcon />}} />}}
                {{canOperateIntegrations && <Menu.Item to="/_integration_run" primaryText="Integration runs" leftIcon={{<IntegrationsIcon />}} />}}
                {{canOperateVersions && <Menu.Item to={{`/${{versionResource}}`}} primaryText="Versions" leftIcon={{<VersionsIcon />}} />}}
             </SubMenu>}}{customization_submenu}
        </Menu>
    );
}};
"""
