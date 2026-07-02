import json

from ....context import Context


def generate(ctx: Context) -> str:
    """Role-profile helpers for custom presentation pages.

    Bakes in the role -> profile-concept mapping resolved by the SchemaProcessor
    (security.roles[].profile_concept) so pages can read and update the record
    linked to the logged-in user without knowing the concept name.
    """
    profile_concepts = ctx.security_config.get("_profile_concepts", [])
    mapping_json = json.dumps(profile_concepts, indent=2)
    return f"""import {{ supabaseClient }} from '../../supabaseClient';

// Role profile concepts ({{ role, concept }}), from security.json roles[].profile_concept.
const PROFILE_CONCEPTS = {mapping_json};

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
"""
