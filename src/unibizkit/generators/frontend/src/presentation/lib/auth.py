from ....context import Context


def generate(ctx: Context) -> str:
    """Session/auth helpers for custom presentation pages.

    Wraps the supabase client so pages don't hand-roll session tracking. When the
    app has an authProvider (authentication_required), getPermissions is re-exported
    from it instead of duplicating the ACL logic.
    """
    auth_required = ctx.security_config["authentication_required"]
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

    return f"""import {{ useState, useEffect }} from 'react';
import {{ supabaseClient }} from '../../supabaseClient';

const BASE_URL = import.meta.env.VITE_BASE_URL;

// Sign in with email and password. Returns the session; throws on failure.
export async function signIn(email, password) {{
  const {{ data, error }} = await supabaseClient.auth.signInWithPassword({{ email, password }});
  if (error) throw new Error(error.message);
  return data.session;
}}

// Register a new account. `metadata` (e.g. {{ first_name, last_name }}) is stored
// as standard Supabase user metadata; when the user's role profile row is created
// server-side, matching profile columns are filled from it.
export async function signUp(email, password, metadata = {{}}) {{
  const {{ data, error }} = await supabaseClient.auth.signUp({{
    email,
    password,
    options: {{ data: metadata, emailRedirectTo: BASE_URL }},
  }});
  if (error) throw new Error(error.message);
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
