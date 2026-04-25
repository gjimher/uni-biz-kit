from ...context import Context


def generate(ctx: Context) -> str:
    base_url = ctx.system_config.get("base_url", "http://localhost:3000")
    sso_enabled = ctx.security_config["sso"]["enabled"]
    allow_registration = ctx.security_config["registration"]["allow"]

    divider_import = ", Divider" if sso_enabled else ""

    # Plain strings (not f-strings) so JSX braces are literal in the output.
    if sso_enabled:
        sso_button = """
const SsoButton = ({ onStart, loading }) => {
    const handleClick = async () => {
        onStart();
    };
    return (
        <Box sx={{ px: 2, pb: 1 }}>
            <Divider sx={{ mb: 2 }}>or</Divider>
            <Button variant="outlined" fullWidth onClick={handleClick} disabled={loading}>
                {loading ? <CircularProgress size={18} /> : 'Login with SSO'}
            </Button>
        </Box>
    );
};
"""
        if allow_registration:
            # Registration is open: show login form directly with SSO button below (no auto-redirect)
            sign_in_content = """const SignInPanel = (props) => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const startSso = async () => {
        setError('');
        setLoading(true);
        try {
            await supabaseClient.auth.signInWithOAuth({
                provider: 'keycloak',
                options: {
                    redirectTo: BASE_URL,
                    scopes: 'openid profile email',
                },
            });
        } catch (err) {
            setError(err.message || 'SSO login failed');
            setLoading(false);
        }
    };

    return (
        <Box sx={{ pt: 2 }}>
            {error && <Alert severity="error" sx={{ px: 2, mb: 1 }}>{error}</Alert>}
            <LoginForm {...props} />
            <SsoButton onStart={startSso} loading={loading} />
        </Box>
    );
};
"""
        else:
            # Registration is closed: auto-redirect to SSO on load
            sign_in_content = """const SignInPanel = (props) => {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [showPasswordLogin, setShowPasswordLogin] = useState(false);
    const hasStartedRef = React.useRef(false);

    const readAuthError = React.useCallback(() => {
        const searchParams = new URLSearchParams(window.location.search);
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        return (
            searchParams.get('error_description') ||
            searchParams.get('error') ||
            hashParams.get('error_description') ||
            hashParams.get('error') ||
            ''
        );
    }, []);

    const startSso = React.useCallback(async () => {
        setError('');
        setLoading(true);
        try {
            await supabaseClient.auth.signInWithOAuth({
                provider: 'keycloak',
                options: {
                    redirectTo: BASE_URL,
                    scopes: 'openid profile email',
                },
            });
        } catch (err) {
            setError(err.message || 'SSO login failed');
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        const authError = readAuthError();
        if (authError) {
            hasStartedRef.current = true;
            setError(decodeURIComponent(authError));
            setLoading(false);
            return;
        }
        if (!showPasswordLogin && !hasStartedRef.current) {
            hasStartedRef.current = true;
            startSso();
        }
    }, [readAuthError, showPasswordLogin, startSso]);

    return (
        <Box sx={{ pt: 2 }}>
            {!showPasswordLogin && (
                <Box sx={{ px: 2, pb: 1 }}>
                    <Alert severity={error ? "error" : "info"} sx={{ mb: 2 }}>
                        {error || 'Redirecting to SSO...'}
                    </Alert>
                    <Button variant="outlined" fullWidth onClick={startSso} disabled={loading}>
                        {loading ? <CircularProgress size={18} /> : 'Retry SSO'}
                    </Button>
                    <Button
                        variant="text"
                        fullWidth
                        sx={{ mt: 1 }}
                        onClick={() => {
                            setShowPasswordLogin(true);
                            setLoading(false);
                        }}
                    >
                        Use email and password
                    </Button>
                </Box>
            )}
            {showPasswordLogin && <>
                <LoginForm {...props} />
                <SsoButton onStart={startSso} loading={loading} />
            </>}
        </Box>
    );
};
"""
    else:
        sso_button = ""
        sign_in_content = ""

    tabs = ""
    if allow_registration:
        tabs = """            <Tabs value={tab} onChange={(_, v) => setTab(v)} centered>
                <Tab label="Sign In" />
                <Tab label="Register" />
            </Tabs>
"""
        tab_body = "{tab === 0 && <SignInPanel {...props} />}\n            {tab === 1 && <RegisterForm />}" if sso_enabled else "{tab === 0 && <LoginForm {...props} />}\n            {tab === 1 && <RegisterForm />}"
        login_component_state = "    const [tab, setTab] = useState(0);\n"
    else:
        tab_body = "<SignInPanel {...props} />" if sso_enabled else "<LoginForm {...props} />"
        login_component_state = ""

    return f"""import * as React from 'react';
import {{ useState }} from 'react';
import {{ useNotify }} from 'react-admin';
import {{ LoginPage, LoginForm }} from 'ra-supabase';
import {{ supabaseClient }} from '../supabaseClient';
import {{ Box, Tab, Tabs, Button, TextField, CircularProgress, Alert{divider_import} }} from '@mui/material';

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
{sso_button}
{sign_in_content}
const LoginWithTabs = (props) => {{
{login_component_state}

    return (
        <Box>
{tabs}            {tab_body}
        </Box>
    );
}};

export const MyLoginPage = props => (
    <LoginPage {{...props}}>
        <LoginWithTabs />
    </LoginPage>
);
"""
