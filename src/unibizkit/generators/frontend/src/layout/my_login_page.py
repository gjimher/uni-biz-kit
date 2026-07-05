from ...context import Context


def generate(ctx: Context) -> str:
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
                    redirectTo: buildSsoRedirectTo(),
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
            <TestUsersButton />
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
                    redirectTo: buildSsoRedirectTo(),
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
                <TestUsersButton />
                <SsoButton onStart={startSso} loading={loading} />
            </>}
        </Box>
    );
};
"""
    else:
        sso_button = ""
        sign_in_content = ""

    # Plain string (not f-string) so JSX braces are literal in the output.
    test_users_button = """
// Demo helper: lets anyone try the app without knowing the seeded credentials.
// Fills the ra-supabase LoginForm inputs through the native value setter so
// react-hook-form picks up the change like a real keystroke.
const fillLoginInput = (name, value) => {
    const input = document.querySelector(`input[name="${name}"]`);
    if (!input) return;
    const setValue = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setValue.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
};

const TestUsersButton = () => {
    const [anchorEl, setAnchorEl] = useState(null);
    if (testUsers.length === 0) return null;

    const pickUser = (user) => {
        fillLoginInput('email', user.email);
        fillLoginInput('password', user.password);
        setAnchorEl(null);
    };

    return (
        <Box sx={{ px: 2, pb: 1 }}>
            <Button variant="outlined" color="secondary" fullWidth onClick={(e) => setAnchorEl(e.currentTarget)}>
                Fill test user
            </Button>
            <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
                {testUsers.map((user) => (
                    <MenuItem key={user.email} onClick={() => pickUser(user)}>
                        <ListItemText primary={user.email} secondary={user.roles.join(', ')} />
                    </MenuItem>
                ))}
            </Menu>
        </Box>
    );
};
"""

    tabs = ""
    if allow_registration:
        tabs = """            <Tabs value={tab} onChange={(_, v) => setTab(v)} centered>
                <Tab label="Sign In" />
                <Tab label="Register" />
            </Tabs>
"""
        tab_body = "{tab === 0 && <SignInPanel {...props} />}\n            {tab === 1 && <RegisterForm />}" if sso_enabled else "{tab === 0 && <><LoginForm {...props} /><TestUsersButton /></>}\n            {tab === 1 && <RegisterForm />}"
        login_component_state = "    const [tab, setTab] = useState(0);\n"
    else:
        tab_body = "<SignInPanel {...props} />" if sso_enabled else "<><LoginForm {...props} /><TestUsersButton /></>"
        login_component_state = ""

    return f"""import * as React from 'react';
import {{ useState }} from 'react';
import {{ useNotify, Notification }} from 'react-admin';
import {{ LoginPage, LoginForm }} from 'ra-supabase';
import {{ supabaseClient }} from '../supabaseClient';
import {{ testUsers }} from '../presentation/lib/auth';
import {{ Box, Tab, Tabs, Button, TextField, CircularProgress, Alert, Menu, MenuItem, ListItemText{divider_import} }} from '@mui/material';

const BASE_URL = import.meta.env.VITE_BASE_URL;
if (!BASE_URL) throw new Error('VITE_BASE_URL is required');
const SSO_REDIRECT_PARAM = 'sso_redirect';
const POST_LOGIN_REDIRECT_KEY = 'unibizkit_post_login_redirect';

const readRedirectTo = () => {{
    const searchRedirect = new URLSearchParams(window.location.search).get('redirectTo');
    if (searchRedirect) return searchRedirect;

    const queryStart = window.location.hash.indexOf('?');
    if (queryStart === -1) return localStorage.getItem(POST_LOGIN_REDIRECT_KEY) || '';

    return (
        new URLSearchParams(window.location.hash.slice(queryStart + 1)).get('redirectTo') ||
        localStorage.getItem(POST_LOGIN_REDIRECT_KEY) ||
        ''
    );
}};

const toHashPath = (target) => {{
    if (!target) return '#/admin';
    if (target.startsWith('#/')) return target;
    if (target.startsWith('/')) return `#${{target}}`;
    return `#/${{target}}`;
}};

const buildSsoRedirectTo = () => {{
    const url = new URL(BASE_URL, window.location.origin);
    url.searchParams.set(SSO_REDIRECT_PARAM, toHashPath(readRedirectTo()));
    return url.toString();
}};

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
{test_users_button}{sso_button}
{sign_in_content}
const LoginWithTabs = (props) => {{
{login_component_state}

    return (
        <Box>
{tabs}            {tab_body}
            <Box sx={{{{ px: 2, pb: 2, textAlign: 'center' }}}}>
                <Button href="#/" variant="text" size="small">
                    Back to home
                </Button>
            </Box>
        </Box>
    );
}};

// Returns the user to a storefront page after login when the login URL carries a
// `redirectTo` parameter (e.g. ?redirectTo=%23%2F?add=42 from "add to cart").
// React-Admin's own post-login redirect is confined to the /admin basename and
// cannot reach a storefront hash route, so we perform the jump ourselves once a
// session exists. The deferred hash write wins over React-Admin's default nav.
const StorefrontRedirectOnLogin = () => {{
    React.useEffect(() => {{
        const redirect = readRedirectTo();
        if (!redirect) return;
        const target = toHashPath(redirect);
        if (target.startsWith('#/admin')) return;
        const {{ data: {{ subscription }} }} = supabaseClient.auth.onAuthStateChange((_event, session) => {{
            if (session) {{
                setTimeout(() => {{ window.location.hash = target; }}, 0);
            }}
        }});
        return () => subscription.unsubscribe();
    }}, []);
    return null;
}};

export const MyLoginPage = props => (
    <LoginPage {{...props}}>
        <StorefrontRedirectOnLogin />
        <LoginWithTabs />
        <Notification />
    </LoginPage>
);
"""
