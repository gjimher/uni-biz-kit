def generate() -> str:
    return """import * as React from 'react';
import {
    Dialog, DialogTitle, DialogContent, DialogActions,
    Button, Typography, Chip, Box
} from '@mui/material';

export const UserProfileDialog = ({ open, onClose, identity }) => {
    if (!identity) return null;
    const roles = identity.roles || [];
    return (
        <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
            <DialogTitle>User Profile</DialogTitle>
            <DialogContent>
                <Typography variant="body1" gutterBottom>
                    <strong>Email:</strong> {identity.fullName}
                </Typography>
                <Typography variant="body1" component="div">
                    <strong>Roles:</strong>
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1 }}>
                    {roles.length > 0
                        ? roles.map((role) => (
                            <Chip key={role} label={role} color="primary" variant="outlined" />
                        ))
                        : <Typography variant="body2" color="text.secondary">No roles assigned</Typography>
                    }
                </Box>
            </DialogContent>
            <DialogActions>
                {/* The change-password flow is a customizable presentation page. */}
                <Button href="#/change-password">Change Password</Button>
                <Button onClick={onClose}>Close</Button>
            </DialogActions>
        </Dialog>
    );
};
"""
