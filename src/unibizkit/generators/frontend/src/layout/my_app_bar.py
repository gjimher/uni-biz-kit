def generate() -> str:
    return """import * as React from 'react';
import { AppBar, Logout, UserMenu, useGetIdentity, useUserMenu } from 'react-admin';
import { MenuItem, ListItemIcon, ListItemText } from '@mui/material';
import { AccountCircle as AccountCircleIcon } from '@mui/icons-material';
import { UserProfileDialog } from './UserProfileDialog';

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
            } />
            <UserProfileDialog open={profileOpen} onClose={() => setProfileOpen(false)} identity={identity} />
        </ProfileContext.Provider>
    );
};
"""
