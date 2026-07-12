import json

from ...context import Context


def gates(ctx: Context) -> list:
    """One entry per role profile concept that has required "ask_after_login" fields.

    Field specs carry what the dialog needs to render and validate the inputs.
    """
    result = []
    for mapping in ctx.security_config["_profile_concepts"]:
        concept = ctx.concept_map[mapping["concept"]]
        fields = []
        for field in concept["fields"]:
            if field["required"] != "ask_after_login":
                continue
            spec = {
                "name": field["name"],
                "label": field["name"].replace("_", " ").capitalize(),
                "description": field["description"],
            }
            if "min_length" in field:
                spec["minLength"] = field["min_length"]
            if "max_length" in field:
                spec["maxLength"] = field["max_length"]
            fields.append(spec)
        if fields:
            result.append({
                "role": mapping["role"],
                "concept": mapping["concept"],
                "fields": fields,
            })
    return result


def generate(ctx: Context) -> str:
    gates_json = json.dumps(gates(ctx), indent=2)
    return f"""import * as React from 'react';
import {{
    Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
    Button, TextField, Alert
}} from '@mui/material';
import {{ supabaseClient }} from '../supabaseClient';

// Role profile concepts with required "ask_after_login" fields. The profile row
// is auto-created at login (see sync_role_profiles); this dialog collects the
// mandatory fields that are still empty and blocks the admin UI until saved.
const PROFILE_GATES = {gates_json};

export const ProfileCompletionDialog = () => {{
    const [gate, setGate] = React.useState(null); // {{ concept, recordId, fields }}
    const [values, setValues] = React.useState({{}});
    const [error, setError] = React.useState('');
    const [saving, setSaving] = React.useState(false);

    const check = React.useCallback(async (session) => {{
        if (!session) {{
            setGate(null);
            return;
        }}
        const roles = session.user.app_metadata?.roles ?? [];
        for (const g of PROFILE_GATES) {{
            if (!roles.includes(g.role)) continue;
            const {{ data }} = await supabaseClient
                .from(g.concept)
                .select('*')
                .eq('_user', session.user.id)
                .maybeSingle();
            if (!data) continue;
            const missing = g.fields.filter((f) => data[f.name] == null || data[f.name] === '');
            if (missing.length > 0) {{
                setValues({{}});
                setError('');
                setGate({{ concept: g.concept, recordId: data.id, fields: missing }});
                return;
            }}
        }}
        setGate(null);
    }}, []);

    React.useEffect(() => {{
        supabaseClient.auth.getSession().then(({{ data: {{ session }} }}) => check(session));
        const {{ data: {{ subscription }} }} = supabaseClient.auth.onAuthStateChange((event, session) => {{
            if (event === 'SIGNED_IN' || event === 'SIGNED_OUT' || event === 'USER_UPDATED') {{
                check(session);
            }}
        }});
        return () => subscription.unsubscribe();
    }}, [check]);

    if (!gate) return null;

    const validate = () => {{
        for (const f of gate.fields) {{
            const value = (values[f.name] ?? '').trim();
            if (!value) return `${{f.label}} is required`;
            if (f.minLength && value.length < f.minLength) {{
                return `${{f.label}} must be at least ${{f.minLength}} characters`;
            }}
            if (f.maxLength && value.length > f.maxLength) {{
                return `${{f.label}} must be at most ${{f.maxLength}} characters`;
            }}
        }}
        return '';
    }};

    const handleSubmit = async (e) => {{
        e.preventDefault();
        const validationError = validate();
        if (validationError) {{
            setError(validationError);
            return;
        }}
        setSaving(true);
        setError('');
        const updateFields = {{}};
        for (const f of gate.fields) {{
            updateFields[f.name] = values[f.name].trim();
        }}
        const {{ error: updateError }} = await supabaseClient
            .from(gate.concept)
            .update(updateFields)
            .eq('id', gate.recordId);
        setSaving(false);
        if (updateError) {{
            setError(updateError.message);
            return;
        }}
        setGate(null);
    }};

    return (
        <Dialog open maxWidth="xs" fullWidth disableEscapeKeyDown>
            <DialogTitle>Complete your profile</DialogTitle>
            <form onSubmit={{handleSubmit}}>
                <DialogContent>
                    <DialogContentText sx={{{{ mb: 1 }}}}>
                        Please fill in the following required information.
                    </DialogContentText>
                    {{error && <Alert severity="error" sx={{{{ mb: 1 }}}}>{{error}}</Alert>}}
                    {{gate.fields.map((f) => (
                        <TextField
                            key={{f.name}}
                            label={{f.label}}
                            helperText={{f.description}}
                            value={{values[f.name] ?? ''}}
                            onChange={{(e) => setValues({{ ...values, [f.name]: e.target.value }})}}
                            fullWidth
                            margin="normal"
                            required
                            inputProps={{{{ maxLength: f.maxLength }}}}
                        />
                    ))}}
                </DialogContent>
                <DialogActions>
                    <Button type="submit" variant="contained" disabled={{saving}}>
                        Save
                    </Button>
                </DialogActions>
            </form>
        </Dialog>
    );
}};
"""
