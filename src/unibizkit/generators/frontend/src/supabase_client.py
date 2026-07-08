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

export const supabaseClient = createClient(supabaseUrl, supabaseKey, {{
    auth: {{
        detectSessionInUrl: {detect_session_in_url},
        // Each model must keep its own credential storage so apps on the same origin do not share sessions.
        storageKey: '{storage_key}',
    }},
}});
"""
