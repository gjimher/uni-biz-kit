from ..context import Context


def generate(ctx: Context) -> str:
    sso_enabled = ctx.security_config["sso"]["enabled"]
    detect_session_in_url = 'true' if sso_enabled else 'false'
    return f"""import {{ createClient }} from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_KEY;

export const supabaseClient = createClient(supabaseUrl, supabaseKey, {{
    auth: {{ detectSessionInUrl: {detect_session_in_url} }},
}});
"""
