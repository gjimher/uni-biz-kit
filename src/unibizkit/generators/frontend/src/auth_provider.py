import json
from ..context import Context


def generate(ctx: Context) -> str:
    rules_json = json.dumps(ctx.security_config["_acl"], indent=4)
    role_names_json = json.dumps([role["name"] for role in ctx.security_config["roles"]], indent=4)
    return f"""import {{ supabaseAuthProvider }} from 'ra-supabase';
import {{ supabaseClient }} from './supabaseClient';

const RULES = {rules_json};
const VALID_ROLES = new Set({role_names_json});

const normalizeRoles = (candidate) => Array.isArray(candidate)
    ? [...new Set(candidate.filter(role => VALID_ROLES.has(role)))]
    : [];

const extractRoles = (user) => normalizeRoles(user.app_metadata?.roles);

const isMissingSessionError = (error) => error?.name === 'AuthSessionMissingError';

const redirectToLogin = {{ message: false, redirectTo: '/login' }};

const clearLocalSession = async () => {{
    try {{
        await supabaseClient.auth.signOut();
    }} catch {{
        // signOut clears the local session even when the server rejects the stale token.
    }}
}};

const buildPermissions = (user) => {{
    const roles = extractRoles(user);
    const permissions = {{}};

    for (const [concept, acl] of Object.entries(RULES)) {{
        const mainRules = acl._main || {{}};
        const fieldRules = acl._fields || {{}};

        for (const role of roles) {{
            const mainAccess = mainRules[role];
            if (mainAccess) {{
                if (!permissions[concept]) permissions[concept] = [];
                if (!permissions[concept].includes(mainAccess)) {{
                    permissions[concept].push(mainAccess);
                }}
                if (mainAccess === 'owner_write' && !permissions[concept].includes('write')) {{
                    permissions[concept].push('write');
                }}
            }}

            for (const [field, fRules] of Object.entries(fieldRules)) {{
                const fieldAccess = fRules[role] || mainAccess;
                if (fieldAccess) {{
                    const fieldKey = `${{concept}}.${{field}}`;
                    if (!permissions[fieldKey]) permissions[fieldKey] = [];
                    if (!permissions[fieldKey].includes(fieldAccess)) {{
                        permissions[fieldKey].push(fieldAccess);
                    }}
                    if (fieldAccess === 'owner_write' && !permissions[fieldKey].includes('write')) {{
                        permissions[fieldKey].push('write');
                    }}
                }}
            }}
        }}
    }}
    return permissions;
}};

const baseAuthProvider = supabaseAuthProvider(supabaseClient, {{}});

export const authProvider = {{
    ...baseAuthProvider,

    checkAuth: async (params) => {{
        try {{
            await baseAuthProvider.checkAuth(params);
            const {{ data, error }} = await supabaseClient.auth.getUser();
            if (error || !data.user) {{
                await clearLocalSession();
                throw redirectToLogin;
            }}
        }} catch (error) {{
            if (error?.redirectTo) throw error;
            throw redirectToLogin;
        }}
    }},

    // ra-supabase-core swallows getUser() errors (deleted user, invalid session) by returning
    // undefined instead of throwing. We override both methods to propagate the AuthError so that
    // ra-core's logoutIfAccessDenied → checkError chain can trigger the logout redirect.
    getIdentity: async () => {{
        const {{ data, error }} = await supabaseClient.auth.getUser();
        if (error) throw error;
        if (!data.user) throw new Error('No authenticated user');
        return {{ id: data.user.id, fullName: data.user.email, email: data.user.email, roles: extractRoles(data.user) }};
    }},

    getPermissions: async () => {{
        const {{ data, error }} = await supabaseClient.auth.getUser();
        if (error) {{
            if (isMissingSessionError(error)) return null;
            throw error;
        }}
        if (!data.user) return null;
        return buildPermissions(data.user);
    }},

    logout: async () => {{
        // ra-supabase throws if signOut returns a server error (e.g. deleted user / expired
        // session), which prevents useLogout's .then() from running and blocks post-logout
        // navigation. Supabase JS always clears the local session regardless of server errors.
        await supabaseClient.auth.signOut();
        return '/';
    }},
}};
"""
