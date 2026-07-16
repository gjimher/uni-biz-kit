import json

from ....context import Context


def gates(ctx: Context) -> list:
    """One entry per role profile concept that has required "ask_after_login" fields.

    Field specs carry what a completion form needs to render and validate the
    inputs. Shared by the generated ProfileCompletionDialog (admin UI) and the
    default complete-profile presentation page.
    """
    result = []
    for mapping in ctx.security_config["_profile_concepts"]:
        concept = ctx.concept_map[mapping["concept"]]
        fields = []
        for field in concept["fields"]:
            if field["required"] != "ask_after_login":
                continue
            spec = {
                "name": field["name"],
                "label": field["name"].replace("_", " ").capitalize(),
                "description": field["description"],
            }
            if "min_length" in field:
                spec["minLength"] = field["min_length"]
            if "max_length" in field:
                spec["maxLength"] = field["max_length"]
            fields.append(spec)
        if fields:
            result.append({
                "role": mapping["role"],
                "concept": mapping["concept"],
                "fields": fields,
            })
    return result


def generate(ctx: Context) -> str:
    """Role-profile helpers for custom presentation pages.

    Bakes in the role -> profile-concept mapping resolved by the SchemaProcessor
    (security.roles[].profile_concept) so pages can read and update the record
    linked to the logged-in user without knowing the concept name, plus the
    profile-completion gates (required "ask_after_login" fields).
    """
    profile_concepts = ctx.security_config.get("_profile_concepts", [])
    mapping_json = json.dumps(profile_concepts, indent=2)
    gates_json = json.dumps(gates(ctx), indent=2)
    return f"""import {{ useState, useEffect }} from 'react';
import {{ useNavigate }} from 'react-router-dom';
import {{ supabaseClient }} from '../../supabaseClient';

// Role profile concepts ({{ role, concept }}), from security.json roles[].profile_concept.
const PROFILE_CONCEPTS = {mapping_json};

// Role profile concepts with required "ask_after_login" fields. The profile row
// is auto-created at login (see sync_role_profiles); these field specs carry
// what a completion form needs to render and validate the missing fields.
const PROFILE_GATES = {gates_json};

// Returns {{ concept, record }} for the logged-in user's profile row, or null when
// signed out or when no profile concept holds a row linked to the user.
export async function getProfile() {{
  const {{ data: {{ user }} }} = await supabaseClient.auth.getUser();
  if (!user) return null;
  const seen = new Set();
  for (const {{ concept }} of PROFILE_CONCEPTS) {{
    if (seen.has(concept)) continue;
    seen.add(concept);
    const {{ data }} = await supabaseClient
      .from(concept)
      .select('*')
      .eq('_user', user.id)
      .maybeSingle();
    if (data) return {{ concept, record: data }};
  }}
  return null;
}}

// Updates the logged-in user's profile row and returns the updated record.
export async function updateProfile(fields) {{
  const profile = await getProfile();
  if (!profile) throw new Error('No profile found for the current user');
  const {{ data, error }} = await supabaseClient
    .from(profile.concept)
    .update(fields)
    .eq('id', profile.record.id)
    .select('*')
    .single();
  if (error) throw new Error(error.message);
  return data;
}}

// React hook that tracks the logged-in user's profile row reactively.
// Returns `undefined` while loading, then null (signed out / no profile row)
// or {{ concept, record }}. Re-reads after profile updates via refresh().
export function useProfile() {{
  const [profile, setProfile] = useState(undefined);
  useEffect(() => {{
    let cancelled = false;
    const refresh = () => getProfile().then((p) => {{ if (!cancelled) setProfile(p); }});
    refresh();
    const {{ data: {{ subscription }} }} = supabaseClient.auth.onAuthStateChange((event) => {{
      if (event === 'SIGNED_IN' || event === 'SIGNED_OUT' || event === 'USER_UPDATED') refresh();
    }});
    return () => {{ cancelled = true; subscription.unsubscribe(); }};
  }}, []);
  return profile;
}}

// Mandatory profile fields ("ask_after_login") still empty for the logged-in
// user: {{ concept, recordId, fields: [{{ name, label, description, ... }}] }},
// or null when nothing is missing (or signed out).
export async function getMissingProfileFields() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (!session) return null;
  const roles = session.user.app_metadata?.roles ?? [];
  for (const gate of PROFILE_GATES) {{
    if (!roles.includes(gate.role)) continue;
    const {{ data }} = await supabaseClient
      .from(gate.concept)
      .select('*')
      .eq('_user', session.user.id)
      .maybeSingle();
    if (!data) continue;
    const missing = gate.fields.filter((f) => data[f.name] == null || data[f.name] === '');
    if (missing.length > 0) return {{ concept: gate.concept, recordId: data.id, fields: missing }};
  }}
  return null;
}}

// Validate values for a list of profile field specs (required + min/max length).
// Returns a display message for the first problem, or '' when all pass.
export function validateProfileFields(fields, values) {{
  for (const f of fields) {{
    const value = (values[f.name] ?? '').trim();
    if (!value) return `${{f.label}} is required`;
    if (f.minLength && value.length < f.minLength) {{
      return `${{f.label}} must be at least ${{f.minLength}} characters`;
    }}
    if (f.maxLength && value.length > f.maxLength) {{
      return `${{f.label}} must be at most ${{f.maxLength}} characters`;
    }}
  }}
  return '';
}}

// Global profile-completion gate for custom UIs: redirects to /complete-profile
// whenever the signed-in user still has mandatory ("ask_after_login") fields to
// fill — however the session arrived (password login, registration confirmation
// link, SSO). Mounted once by the PresentationRouter. The admin backoffice
// (#/admin) is skipped because its blocking dialog owns that gate, and the
// password-recovery flow (#/set-password) must not be interrupted.
export function useProfileGateRedirect() {{
  const navigate = useNavigate();
  useEffect(() => {{
    let cancelled = false;
    const check = () => {{
      getMissingProfileFields().then((missing) => {{
        if (cancelled || !missing) return;
        const current = window.location.hash.replace(/^#/, '') || '/';
        if (current.startsWith('/admin') || current.startsWith('/complete-profile') || current.startsWith('/set-password')) {{
          return;
        }}
        navigate('/complete-profile', {{ state: {{ nextPathname: current }} }});
      }});
    }};
    check();
    const {{ data: {{ subscription }} }} = supabaseClient.auth.onAuthStateChange((event) => {{
      if (event === 'SIGNED_IN' || event === 'USER_UPDATED') check();
    }});
    return () => {{ cancelled = true; subscription.unsubscribe(); }};
  }}, [navigate]);
}}

// Save the completed fields for a gate returned by getMissingProfileFields.
export async function completeProfileFields(gate, values) {{
  const updateFields = {{}};
  for (const f of gate.fields) updateFields[f.name] = (values[f.name] ?? '').trim();
  const {{ error }} = await supabaseClient
    .from(gate.concept)
    .update(updateFields)
    .eq('id', gate.recordId);
  if (error) throw new Error(error.message);
}}
"""
