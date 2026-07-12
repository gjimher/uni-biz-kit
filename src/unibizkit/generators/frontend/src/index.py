def generate() -> str:
    return """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

if (!import.meta.env.VITE_BASE_URI) throw new Error('VITE_BASE_URI is required');
if (!import.meta.env.VITE_SUPABASE_URL) throw new Error('VITE_SUPABASE_URL is required');
if (!import.meta.env.VITE_SUPABASE_KEY) throw new Error('VITE_SUPABASE_KEY is required');

// The Supabase recovery-link callback is handled in supabaseClient.js: it must
// run before createClient, and imports are hoisted above this module's body.

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);"""
