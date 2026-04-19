def generate() -> str:
    return """import * as React from 'react';
import { useNotify } from 'react-admin';
import {
    Dialog, DialogTitle, DialogContent, DialogActions,
    Button, TextField, CircularProgress, Box
} from '@mui/material';
import { supabaseClient } from '../supabaseClient';

export const ChangePasswordDialog = ({ open, onClose }) => {
    const notify = useNotify();
    const [currentPassword, setCurrentPassword] = React.useState('');
    const [newPassword, setNewPassword] = React.useState('');
    const [confirmPassword, setConfirmPassword] = React.useState('');
    const [loading, setLoading] = React.useState(false);

    const handleClose = () => {
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
        onClose();
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!currentPassword) {
            notify('Please enter your current password.', { type: 'warning' });
            return;
        }
        if (!newPassword) {
            notify('Please enter a new password.', { type: 'warning' });
            return;
        }
        if (newPassword !== confirmPassword) {
            notify('New passwords do not match.', { type: 'warning' });
            return;
        }
        if (newPassword.length < 6) {
            notify('New password must be at least 6 characters.', { type: 'warning' });
            return;
        }
        setLoading(true);
        const { data: { user }, error: getUserError } = await supabaseClient.auth.getUser();
        if (getUserError || !user?.email) {
            notify('Could not retrieve current user.', { type: 'error' });
            setLoading(false);
            return;
        }
        const { error: signInError } = await supabaseClient.auth.signInWithPassword({
            email: user.email,
            password: currentPassword,
        });
        if (signInError) {
            notify('Current password is incorrect.', { type: 'error' });
            setLoading(false);
            return;
        }
        const { error: updateError } = await supabaseClient.auth.updateUser({ password: newPassword });
        setLoading(false);
        if (updateError) {
            notify(updateError.message, { type: 'error' });
        } else {
            notify('Password updated successfully.', { type: 'success' });
            handleClose();
        }
    };

    return (
        <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
            <DialogTitle>Change Password</DialogTitle>
            <Box component="form" onSubmit={handleSubmit}>
                <DialogContent>
                    <TextField
                        label="Current Password"
                        type="password"
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        fullWidth
                        margin="normal"
                        autoComplete="current-password"
                        disabled={loading}
                    />
                    <TextField
                        label="New Password"
                        type="password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        fullWidth
                        margin="normal"
                        autoComplete="new-password"
                        disabled={loading}
                    />
                    <TextField
                        label="Confirm New Password"
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        fullWidth
                        margin="normal"
                        autoComplete="new-password"
                        disabled={loading}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleClose} disabled={loading}>Cancel</Button>
                    <Button type="submit" variant="contained" disabled={loading}>
                        {loading ? <CircularProgress size={20} /> : 'Update Password'}
                    </Button>
                </DialogActions>
            </Box>
        </Dialog>
    );
};
"""
