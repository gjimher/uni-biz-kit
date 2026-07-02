def generate() -> str:
    """Supabase Storage helpers for custom presentation pages."""
    return """import { supabaseClient } from '../../supabaseClient';

// Public URL for an object in a public storage bucket. Returns null for empty paths.
export function publicUrl(bucket, path) {
  if (!path) return null;
  return supabaseClient.storage.from(bucket).getPublicUrl(path).data.publicUrl;
}

// Signed (time-limited) URL for an object in a private bucket.
export async function signedUrl(bucket, path, expiresInSeconds = 3600) {
  if (!path) return null;
  const { data, error } = await supabaseClient.storage.from(bucket).createSignedUrl(path, expiresInSeconds);
  if (error) throw error;
  return data.signedUrl;
}
"""
