def generate() -> str:
    """Backend-function error reading, shared by every caller of an edge function."""
    return """// Reading the message a backend function actually sent back.
//
// supabase-js reports a non-2xx reply as an error whose `context` is the raw
// Response — the body it carries (a rule rejection, a permission refusal) is only
// available by reading it. Without this, every 4xx surfaces to the user as
// "Edge Function returned a non-2xx status code" and the real reason is lost.
export async function functionErrorMessage(error, fallback) {
  let body = error?.context;
  if (body && typeof body.json === 'function') {
    // Clone it: the caller may still want to read the response itself.
    try { body = await body.clone().json(); } catch { body = null; }
  } else if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { body = null; }
  }
  return body?.error || error?.message || fallback;
}
"""
