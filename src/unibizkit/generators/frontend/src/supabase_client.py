def generate() -> str:
    return """import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseKey = process.env.REACT_APP_SUPABASE_KEY;

export const supabaseClient = createClient(supabaseUrl, supabaseKey, {
    auth: { detectSessionInUrl: false },
});
"""
