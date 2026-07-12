from ..context import Context


def generate(ctx: Context) -> str:
    sso_enabled = ctx.security_config["sso"]["enabled"]
    # Both OAuth (SSO) and the email signup-confirmation link return their tokens in
    # the URL hash, so the client must parse them to establish the session. Enable it
    # whenever either flow can occur, otherwise the confirmation link lands on a blank
    # page with an unconsumed #access_token=... hash.
    registration_allowed = ctx.security_config["registration"]["allow"]
    detect_session_in_url = 'true' if (sso_enabled or registration_allowed) else 'false'
    base_uri = ctx.deployment_config.get("base_uri", "/")
    storage_prefix = base_uri.strip("/") or "root"
    storage_key = f"{storage_prefix}-supabase-auth-token"
    return f"""import {{ createClient }} from '@supabase/supabase-js';

const supabaseUrl = window.location.origin + import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_KEY;

// Handle the recovery-link callback BEFORE the client is created. Supabase
// emails link to the root URL with the tokens in the hash; rewrite that into
// the /set-password SPA route (replaceState: no request, no reload). Doing it
// here — not in index.jsx, whose imports are hoisted above its body — ensures
// supabase-js only ever sees the rewritten URL: since supabase-js 2.107 the
// lockless _initialize parses the URL synchronously at createClient, and if it
// saw the original tokens it would consume them and clear the hash mid-render,
// yanking the router off /set-password. The rewritten URL (access/refresh
// token only, no type/expires_in) fails its callback validation harmlessly, so
// every version leaves the tokens for the set-password page to consume.
const _hashParams = new URLSearchParams(window.location.hash.substring(1));
if (_hashParams.get('type') === 'recovery' && _hashParams.get('access_token') && _hashParams.get('refresh_token')) {{
    window.history.replaceState({{}}, '', import.meta.env.VITE_BASE_URI + '#/set-password?access_token=' + encodeURIComponent(_hashParams.get('access_token')) + '&refresh_token=' + encodeURIComponent(_hashParams.get('refresh_token')));
}}

export const supabaseClient = createClient(supabaseUrl, supabaseKey, {{
    auth: {{
        detectSessionInUrl: {detect_session_in_url},
        // Each model must keep its own credential storage so apps on the same origin do not share sessions.
        storageKey: '{storage_key}',
    }},
}});

// Safety net for supabase-js versions that do consume a recovery URL before
// the rewrite above can hide it: PASSWORD_RECOVERY only fires once the session
// is saved (and the hash cleared), so route back to the set-password page,
// which updates the password on the live session when no tokens are left.
supabaseClient.auth.onAuthStateChange((event) => {{
    if (event === 'PASSWORD_RECOVERY') {{
        window.location.hash = '#/set-password';
    }}
}});
"""
