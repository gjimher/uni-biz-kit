def generate() -> str:
    return """import * as React from 'react';
import {
    Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
    Button, TextField, Alert
} from '@mui/material';
import { supabaseClient } from '../supabaseClient';
import {
    getMissingProfileFields, validateProfileFields, completeProfileFields
} from '../presentation/lib/profile';

// Blocks the admin UI right after login until the mandatory "ask_after_login"
// profile fields are filled. The gate data and checks live in the presentation
// lib, so custom pages can build the same flow (see pages/complete-profile.jsx).
export const ProfileCompletionDialog = () => {
    const [gate, setGate] = React.useState(null); // { concept, recordId, fields }
    const [values, setValues] = React.useState({});
    const [error, setError] = React.useState('');
    const [saving, setSaving] = React.useState(false);

    const check = React.useCallback(async () => {
        const missing = await getMissingProfileFields();
        setValues({});
        setError('');
        setGate(missing);
    }, []);

    React.useEffect(() => {
        check();
        const { data: { subscription } } = supabaseClient.auth.onAuthStateChange((event) => {
            if (event === 'SIGNED_IN' || event === 'SIGNED_OUT' || event === 'USER_UPDATED') {
                check();
            }
        });
        return () => subscription.unsubscribe();
    }, [check]);

    if (!gate) return null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        const validationError = validateProfileFields(gate.fields, values);
        if (validationError) {
            setError(validationError);
            return;
        }
        setSaving(true);
        setError('');
        try {
            await completeProfileFields(gate, values);
            setGate(null);
        } catch (saveError) {
            setError(saveError.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open maxWidth="xs" fullWidth disableEscapeKeyDown>
            <DialogTitle>Complete your profile</DialogTitle>
            <form onSubmit={handleSubmit}>
                <DialogContent>
                    <DialogContentText sx={{ mb: 1 }}>
                        Please fill in the following required information.
                    </DialogContentText>
                    {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
                    {gate.fields.map((f) => (
                        <TextField
                            key={f.name}
                            label={f.label}
                            helperText={f.description}
                            value={values[f.name] ?? ''}
                            onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                            fullWidth
                            margin="normal"
                            required
                            inputProps={{ maxLength: f.maxLength }}
                        />
                    ))}
                </DialogContent>
                <DialogActions>
                    <Button type="submit" variant="contained" disabled={saving}>
                        Save
                    </Button>
                </DialogActions>
            </form>
        </Dialog>
    );
};
"""
