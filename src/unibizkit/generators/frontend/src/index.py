def generate() -> str:
    return """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

if (!import.meta.env.VITE_BASE_URI) throw new Error('VITE_BASE_URI is required');
if (!(import.meta.env.VITE_API_URL ?? import.meta.env.VITE_SUPABASE_URL)) throw new Error('VITE_SUPABASE_URL (or VITE_API_URL) is required');
if (!import.meta.env.VITE_SUPABASE_KEY) throw new Error('VITE_SUPABASE_KEY is required');

// Handle Supabase auth callback before React mounts.
// Supabase emails link to the root URL with auth tokens in the hash.
// The root URL always serves index.html (unlike /set-password which may not).
// Here we convert the hash params into the correct SPA path using replaceState
// (no server request, no page reload — browser already has index.html loaded).
// Supabase's _initialize() already read the hash synchronously before this
// runs, so it still processes the tokens and fires PASSWORD_RECOVERY if valid.
const _hash = window.location.hash.substring(1);
if (_hash) {
    const _hashParams = new URLSearchParams(_hash);
    const _accessToken = _hashParams.get('access_token');
    const _refreshToken = _hashParams.get('refresh_token');
    const _type = _hashParams.get('type');
    if (_type === 'recovery' && _accessToken && _refreshToken) {
        window.history.replaceState({}, '', import.meta.env.VITE_BASE_URI + '#/set-password?access_token=' + encodeURIComponent(_accessToken) + '&refresh_token=' + encodeURIComponent(_refreshToken));
    }
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);"""
