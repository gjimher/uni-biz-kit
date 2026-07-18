_TEMPLATE = """import * as React from 'react';
import { __RA_IMPORTS__ } from 'react-admin';
import { MenuItem, ListItemIcon, ListItemText } from '@mui/material';
import { AccountCircle as AccountCircleIcon } from '@mui/icons-material';
import { UserProfileDialog } from './UserProfileDialog';
__CUSTOM_IMPORT__
const ProfileContext = React.createContext();

const ProfileMenuItem = React.forwardRef((props, ref) => {
    const { onClose: closeMenu } = useUserMenu();
    const openProfile = React.useContext(ProfileContext);
    const handleClick = () => {
        closeMenu();
        openProfile();
    };
    return (
        <MenuItem ref={ref} onClick={handleClick} {...props}>
            <ListItemIcon><AccountCircleIcon fontSize="small" /></ListItemIcon>
            <ListItemText>Profile</ListItemText>
        </MenuItem>
    );
});

export const MyAppBar = () => {
    const [profileOpen, setProfileOpen] = React.useState(false);
    const { data: identity } = useGetIdentity();
    return (
        <ProfileContext.Provider value={() => setProfileOpen(true)}>
            <AppBar userMenu={
                <UserMenu>
                    <ProfileMenuItem />
                    <Logout />
                </UserMenu>
            __APP_BAR_CLOSE__
            <UserProfileDialog open={profileOpen} onClose={() => setProfileOpen(false)} identity={identity} />
        </ProfileContext.Provider>
    );
};
"""

_APP_BAR_CHILDREN = """}>
                {/* AppBar children replace the default title, so restore it */}
                <TitlePortal />
                <DevDesignTools />
            </AppBar>"""


def generate(customization: bool) -> str:
    if customization:
        ra_imports = "AppBar, Logout, TitlePortal, UserMenu, useGetIdentity, useUserMenu"
        custom_import = "import { DevDesignTools } from '../components/customization';\n"
        app_bar_close = _APP_BAR_CHILDREN
    else:
        ra_imports = "AppBar, Logout, UserMenu, useGetIdentity, useUserMenu"
        custom_import = ""
        app_bar_close = "} />"
    return (
        _TEMPLATE
        .replace("__RA_IMPORTS__", ra_imports)
        .replace("__CUSTOM_IMPORT__", custom_import)
        .replace("__APP_BAR_CLOSE__", app_bar_close)
    )
