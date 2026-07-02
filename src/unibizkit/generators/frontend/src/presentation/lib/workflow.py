def generate() -> str:
    """Workflow transition helper for custom presentation pages."""
    return """import { supabaseClient } from '../../supabaseClient';

// Move a record through its workflow by invoking the `workflow-transition` edge
// function. Throws an Error with the server-provided message on failure.
export async function transition(concept, id, toState, comment = '') {
  const { data, error } = await supabaseClient.functions.invoke('workflow-transition', {
    body: { concept, id, to_state: toState, comment },
  });
  if (error) {
    let body = error.context;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch { body = null; }
    }
    throw new Error(body?.error || error.message || `Could not move ${concept} to ${toState}`);
  }
  if (data?.ok === false) throw new Error(data.error || `Could not move ${concept} to ${toState}`);
  return data;
}
"""
