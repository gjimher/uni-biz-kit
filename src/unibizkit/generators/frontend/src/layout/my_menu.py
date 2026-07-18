import json
from ...context import Context

# JS snippets present only when the presentation customization system is
# generated (designer 'dev'/'production'); with 'off' the emitted menu matches
# the pre-customization output.

_CUSTOM_IMPORT = "import { useCustomization, DesignBadge } from '../components/customization';\n"

_CUSTOM_ICONS = """    Palette as CustomizationIcon,
    Brush as DesignerIcon,
"""

_RENDER_MENU_CUSTOM = """// Each entry carries its own design badge (targeting the item by path) and
// every level ends with a design-mode-only "Add entry" row — the menu edits
// stay WYSIWYG right in the sidebar.
const RenderMenu = ({ items, state, handleToggle, path = [] }) => {
  return items.map((item, index) => {
     const itemPath = path.concat(index);
     const badge = <DesignBadge target={{ kind: 'menuItem', path: itemPath, name: item.label }} />;
     if (item.children) {
         let Icon = SubMenuIcon;
         if (item.label === 'Security') Icon = SecurityIcon;

         return (
             <SubMenu
                key={item.label}
                name={item.label}
                icon={<Icon />}
                badge={badge}
                isOpen={state[item.label]}
                handleToggle={() => handleToggle(item.label)}
             >
                <RenderMenu items={item.children} state={state} handleToggle={handleToggle} path={itemPath} />
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

_RENDER_MENU_PLAIN = """const RenderMenu = ({ items, state, handleToggle }) => {
  return items.map((item, index) => {
     if (item.children) {
         let Icon = SubMenuIcon;
         if (item.label === 'Security') Icon = SecurityIcon;

         return (
             <SubMenu
                key={item.label}
                name={item.label}
                icon={<Icon />}
                isOpen={state[item.label]}
                handleToggle={() => handleToggle(item.label)}
             >
                <RenderMenu items={item.children} state={state} handleToggle={handleToggle} />
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
import {{ Menu, useGetIdentity, useTranslate }} from 'react-admin';
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
{custom_icons}}} from '@mui/icons-material';

const WORKFLOW_PAGE_ROUTES = {{
    assignable_tasks: '/workflow/assignable',
    my_tasks: '/workflow/mine',
}};

const menuItems = {menu_items_json};
const conceptDescriptions = {concept_descriptions_json};
const integrationRoles = new Set({integration_roles_json});
const hasIntegrations = {has_integrations};
{designer_admin_const}
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
    const [state, setState] = React.useState({{}});
    const handleToggle = (menu) => {{
        setState(state => ({{ ...state, [menu]: !state[menu] }}));
    }};
    const canOperateIntegrations = hasIntegrations && (identity?.roles || []).some(role => integrationRoles.has(role));
{items_setup}
    return (
        <Menu>
            <ListItemButton component="a" href="#/" sx={{{{ pl: 2, py: 1 }}}}>
                <ListItemIcon sx={{{{ minWidth: 40 }}}}>
                    <HomeIcon />
                </ListItemIcon>
                <ListItemText primary="Home" />
            </ListItemButton>
             <RenderMenu items={{{render_items}}} state={{state}} handleToggle={{handleToggle}} />{root_add_badge}
             {{canOperateIntegrations && <SubMenu
                name="Operations"
                icon={{<OperationsIcon />}}
                isOpen={{state.Operations}}
                handleToggle={{() => handleToggle('Operations')}}
             >
                <Menu.Item to="/_integration" primaryText="Integrations" leftIcon={{<IntegrationsIcon />}} />
                <Menu.Item to="/_integration_run" primaryText="Integration runs" leftIcon={{<IntegrationsIcon />}} />
             </SubMenu>}}{customization_submenu}
        </Menu>
    );
}};
"""
