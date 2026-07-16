import json

from ....context import Context


def generate(ctx: Context) -> str:
    """Session/auth helpers for custom presentation pages.

    Wraps the supabase client so pages don't hand-roll session tracking. When the
    app has an authProvider (authentication_required), getPermissions is re-exported
    from it instead of duplicating the ACL logic.

    Error convention: helpers return data and throw Error with a user-displayable
    message; pages render the message wherever fits their design.
    """
    auth_required = ctx.security_config["authentication_required"]
    sso_enabled = ctx.security_config["sso"]["enabled"]
    permissions_block = (
        """
import { authProvider } from '../../authProvider';

// Resolve the current user's permissions object (same shape react-admin uses):
// { '<concept>': ['read'|'write'|...], '<concept>.<field>': [...] }.
export const getPermissions = () => authProvider.getPermissions();
"""
        if auth_required
        else """
// This app has no authProvider (authentication is not required), so there are no
// per-concept permissions to resolve.
export const getPermissions = async () => ({});
"""
    )

    test_users = (
        [
            {"email": u["email"], "password": u["password"], "roles": u["roles"]}
            for u in ctx.security_config["users"]
        ]
        if auth_required
        else []
    )
    test_users_json = json.dumps(test_users, indent=2)

    sso_block = (
        """
// Sign in through the SSO identity provider. Redirects the browser to the
// provider; on return the app lands at BASE_URL and the sso_redirect handler
// (see App.jsx) navigates to `redirectHash` (e.g. '#/admin' or '/priv/area').
export async function signInWithSso(redirectHash = '#/') {
  const url = new URL(BASE_URL, window.location.origin);
  url.searchParams.set('sso_redirect', redirectHash.startsWith('#') ? redirectHash : `#${redirectHash}`);
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: 'keycloak',
    options: { redirectTo: url.toString(), scopes: 'openid profile email' },
  });
  if (error) throw new Error(authErrorMessage(error));
}
"""
        if sso_enabled
        else ""
    )

    return f"""import {{ useState, useEffect }} from 'react';
import {{ useLocation, useNavigate }} from 'react-router-dom';
import {{ supabaseClient }} from '../../supabaseClient';

// All helpers follow the same error convention: they return data and throw
// Error with a user-displayable message. Pages own the presentation — render
// the message inline, in a status bar, or however fits the design.

const BASE_URL = import.meta.env.VITE_BASE_URL;

// Auth backend failures sometimes carry useless messages — supabase-js surfaces
// gateway timeouts/5xx as an AuthRetryableFetchError whose message is literally
// "{{}}". Normalize to something a person can act on.
function authErrorMessage(error) {{
  const message = typeof error?.message === 'string' ? error.message.trim() : '';
  if (message && message !== '{{}}') return message;
  if (error?.status) {{
    return `The authentication service did not respond (HTTP ${{error.status}}). Please try again later.`;
  }}
  return 'Could not reach the authentication service. Please try again later.';
}}

// Seed users from security.json: [{{ email, password, roles }}]. They are baked
// into the bundle so example apps can offer a "fill test user" shortcut on
// login forms — anyone can try the app without knowing the seeded credentials.
export const testUsers = {test_users_json};

// Sign in with email and password. Returns the session; throws on failure.
export async function signIn(email, password) {{
  const {{ data, error }} = await supabaseClient.auth.signInWithPassword({{ email, password }});
  if (error) throw new Error(authErrorMessage(error));
  return data.session;
}}

// Register a new account. `metadata` (e.g. {{ first_name, last_name }}) is stored
// as standard Supabase user metadata; when the user's role profile row is created
// server-side, profile fields with a from_metadata(...) default are filled from it.
export async function signUp(email, password, metadata = {{}}) {{
  const {{ data, error }} = await supabaseClient.auth.signUp({{
    email,
    password,
    options: {{ data: metadata, emailRedirectTo: BASE_URL }},
  }});
  if (error) throw new Error(authErrorMessage(error));
  return data;
}}

// Returns the current Supabase session, or null when signed out.
export async function getSession() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  return session ?? null;
}}

// Returns the current authenticated user, or null when signed out.
export async function getUser() {{
  const {{ data: {{ user }} }} = await supabaseClient.auth.getUser();
  return user ?? null;
}}

// Convenience boolean: is there an active session?
export async function isLoggedIn() {{
  return (await getSession()) != null;
}}

// Sign the current user out.
export async function signOut() {{
  await supabaseClient.auth.signOut();
}}
{sso_block}
// Change the signed-in user's password after verifying the current one.
export async function changePassword(currentPassword, newPassword) {{
  const user = await getUser();
  if (!user?.email) throw new Error('Not signed in.');
  const {{ error: signInError }} = await supabaseClient.auth.signInWithPassword({{
    email: user.email,
    password: currentPassword,
  }});
  if (signInError) throw new Error('Current password is incorrect.');
  const {{ error }} = await supabaseClient.auth.updateUser({{ password: newPassword }});
  if (error) throw new Error(authErrorMessage(error));
}}

// Email a password-recovery link. The link lands back on the app, which
// rewrites it into the /set-password page (see supabaseClient.js).
export async function requestPasswordReset(email) {{
  const {{ error }} = await supabaseClient.auth.resetPasswordForEmail(email, {{ redirectTo: BASE_URL }});
  if (error) throw new Error(authErrorMessage(error));
}}

// Recovery tokens that the recovery-link rewrite (supabaseClient.js) leaves in
// the #/set-password URL for older supabase-js versions. Newer versions
// (>= 2.107) consume the link themselves and hold a live session instead.
function recoveryTokensFromUrl() {{
  const queryIndex = window.location.hash.indexOf('?');
  if (queryIndex === -1) return null;
  const params = new URLSearchParams(window.location.hash.substring(queryIndex + 1));
  const access_token = params.get('access_token');
  const refresh_token = params.get('refresh_token');
  return access_token && refresh_token ? {{ access_token, refresh_token }} : null;
}}

// Is there a usable recovery credential (URL tokens or a live session)?
// A set-password page should bounce to sign-in when this resolves false.
export async function hasPasswordRecovery() {{
  if (recoveryTokensFromUrl()) return true;
  return (await getSession()) != null;
}}

// Set a new password from a recovery link (forgot-password flow): consumes the
// URL tokens when present, otherwise updates the live recovery session. After
// it resolves, navigate with a full page load (window.location.replace) so the
// Supabase client re-initialises from storage — a SPA navigation can leave a
// stale recovery token in memory that PostgREST then rejects.
export async function completePasswordReset(newPassword) {{
  const tokens = recoveryTokensFromUrl();
  if (tokens) {{
    const {{ error }} = await supabaseClient.auth.setSession(tokens);
    if (error) throw new Error(authErrorMessage(error));
  }}
  const {{ error }} = await supabaseClient.auth.updateUser({{ password: newPassword }});
  if (error) throw new Error(authErrorMessage(error));
}}

// Route guard for pages that need a signed-in user: returns the session
// (undefined while it loads) and redirects to `redirectTo` when signed out,
// remembering the current location so the sign-in page can come back here
// after login (see pages/signin.jsx: location.state.nextPathname).
export function useRequireSession(redirectTo = '/signin') {{
  const session = useSession();
  const navigate = useNavigate();
  const {{ pathname, search }} = useLocation();
  useEffect(() => {{
    if (session === null) {{
      navigate(redirectTo, {{ state: {{ nextPathname: pathname, nextSearch: search }} }});
    }}
  }}, [session, navigate, redirectTo, pathname, search]);
  return session;
}}

// React hook that tracks the session reactively.
// Returns `undefined` while loading, then `null` (signed out) or the session.
export function useSession() {{
  const [session, setSession] = useState(undefined);
  useEffect(() => {{
    supabaseClient.auth.getSession().then(({{ data: {{ session }} }}) => setSession(session));
    const {{ data: {{ subscription }} }} = supabaseClient.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => subscription.unsubscribe();
  }}, []);
  return session;
}}
{permissions_block}"""
