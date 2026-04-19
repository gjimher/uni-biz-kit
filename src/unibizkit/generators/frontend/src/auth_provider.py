import json
from ..context import Context


def generate(ctx: Context) -> str:
    rules_json = json.dumps(ctx.security_config["_acl"], indent=4)
    return f"""import {{ supabaseAuthProvider }} from 'ra-supabase';
import {{ supabaseClient }} from './supabaseClient';

const RULES = {rules_json};

export const authProvider = supabaseAuthProvider(supabaseClient, {{
        getIdentity: async (user) => ({{
            id: user.id,
            fullName: user.email,
            roles: user.app_metadata?.roles || []
        }}),
        getPermissions: async (user) => {{
            const roles = user.app_metadata?.roles || [];
            const permissions = {{}};

            // RULES structure: concept -> {{ _main: {{ role: access }}, _fields: {{ field: {{ role: access }} }} }}
            for (const [concept, acl] of Object.entries(RULES)) {{
                const mainRules = acl._main || {{}};
                const fieldRules = acl._fields || {{}};

                for (const role of roles) {{
                    // Concept level access
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

                    // Field level access
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
        }},
    }});
"""
