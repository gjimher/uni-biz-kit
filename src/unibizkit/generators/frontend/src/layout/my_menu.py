import json
from ...context import Context


def generate(ctx: Context) -> str:
    menu_items_json = json.dumps(ctx.presentation_config.get("menu"), indent=2)
    concept_descriptions = {c["name"]: c["description"] for c in ctx.concepts if c["description"]}
    concept_descriptions_json = json.dumps(concept_descriptions)
    return f"""import * as React from 'react';
import {{ Menu, useTranslate }} from 'react-admin';
import {{ Collapse, List, ListItemButton, ListItemIcon, ListItemText }} from '@mui/material';
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
}} from '@mui/icons-material';

const menuItems = {menu_items_json};
const conceptDescriptions = {concept_descriptions_json};

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

         const desc = conceptDescriptions[item.concept];
         const label = desc ? (
           <span style={{{{ display: 'inline-flex', alignItems: 'center', gap: 4 }}}}>
             {{item.label}}
             <Tooltip title={{desc}} placement="right">
               <HelpOutlineIcon sx={{{{ fontSize: 14, cursor: 'help' }}}} />
             </Tooltip>
           </span>
         ) : item.label;
         return <Menu.Item key={{item.concept}} to={{`/${{item.concept}}`}} primaryText={{label}} leftIcon={{Icon}} />;
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
            <ListItemButton component="a" href="#/" sx={{{{ pl: 2, py: 1 }}}}>
                <ListItemIcon sx={{{{ minWidth: 40 }}}}>
                    <HomeIcon />
                </ListItemIcon>
                <ListItemText primary="Home" />
            </ListItemButton>
             <RenderMenu items={{menuItems}} state={{state}} handleToggle={{handleToggle}} />
        </Menu>
    );
}};
"""
