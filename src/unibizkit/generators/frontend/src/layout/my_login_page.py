from ...context import Context


def generate(ctx: Context) -> str:
    base_url = ctx.system_config.get("base_url", "http://localhost:3000")
    return f"""import * as React from 'react';
import {{ useState }} from 'react';
import {{ useNotify }} from 'react-admin';
import {{ LoginPage, LoginForm }} from 'ra-supabase';
import {{ supabaseClient }} from '../supabaseClient';
import {{ Box, Tab, Tabs, Button, TextField, CircularProgress, Alert }} from '@mui/material';

const BASE_URL = '{base_url}';

const RegisterForm = () => {{
    const notify = useNotify();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [registered, setRegistered] = useState(false);
    const [error, setError] = useState('');

    const handleRegister = async (e) => {{
        e.preventDefault();
        setError('');

        if (!email) {{
            setError('Email is required');
            return;
        }}
        if (!password) {{
            setError('Password is required');
            return;
        }}
        if (password !== confirmPassword) {{
            setError('Passwords do not match');
            return;
        }}
        if (password.length < 6) {{
            setError('Password must be at least 6 characters');
            return;
        }}

        setLoading(true);
        try {{
            const {{ data, error: signUpError }} = await supabaseClient.auth.signUp({{
                email,
                password,
                options: {{
                    emailRedirectTo: BASE_URL,
                }}
            }});

            if (signUpError) {{
                setError(signUpError.message);
            }} else {{
                setRegistered(true);
            }}
        }} catch (err) {{
            setError(err.message);
        }} finally {{
            setLoading(false);
        }}
    }};

    if (registered) {{
        return (
            <Box sx={{{{ padding: 2 }}}}>
                <Alert severity="success">
                    Registration successful! Please check your email and click the confirmation link before logging in.
                </Alert>
            </Box>
        );
    }}

    return (
        <Box component="form" onSubmit={{handleRegister}} sx={{{{ padding: 2 }}}}>
            {{error && <Alert severity="error" sx={{{{ mb: 2 }}}}>{{error}}</Alert>}}
            <TextField
                label="Email"
                type="email"
                value={{email}}
                onChange={{e => setEmail(e.target.value)}}
                fullWidth
                margin="normal"
                required
                autoFocus
            />
            <TextField
                label="Password"
                type="password"
                value={{password}}
                onChange={{e => setPassword(e.target.value)}}
                fullWidth
                margin="normal"
                required
                inputProps={{{{ minLength: 6 }}}}
            />
            <TextField
                label="Confirm Password"
                type="password"
                value={{confirmPassword}}
                onChange={{e => setConfirmPassword(e.target.value)}}
                fullWidth
                margin="normal"
                required
            />
            <Button
                type="submit"
                variant="contained"
                fullWidth
                disabled={{loading}}
                sx={{{{ mt: 2 }}}}
            >
                {{loading ? <CircularProgress size={{24}} /> : 'Register'}}
            </Button>
        </Box>
    );
}};

const LoginWithTabs = (props) => {{
    const [tab, setTab] = useState(0);

    return (
        <Box>
            <Tabs value={{tab}} onChange={{(_, v) => setTab(v)}} centered>
                <Tab label="Sign In" />
                <Tab label="Register" />
            </Tabs>
            {{tab === 0 && <LoginForm {{...props}} />}}
            {{tab === 1 && <RegisterForm />}}
        </Box>
    );
}};

export const MyLoginPage = props => (
    <LoginPage {{...props}}>
        <LoginWithTabs />
    </LoginPage>
);
"""
