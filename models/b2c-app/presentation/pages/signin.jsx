import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { signIn, useSession } from '../lib';

// ---------------------------------------------------------------------------
// Storefront sign-in page. Same look & feel as the shop (see index.jsx).
// Supports ?redirectTo=<hash path> so "add to cart" can bounce here and return.
// ---------------------------------------------------------------------------

const ACCENT = '#6366f1';
const INK = '#1e293b';
const MUTED = '#64748b';
const BORDER = '#e2e8f0';
const BG_SOFT = '#f8fafc';
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export default function SignInPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const session = useSession(); // undefined = loading
  const redirectTo = searchParams.get('redirectTo') || '';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const goBack = React.useCallback(() => {
    if (redirectTo.startsWith('#/')) {
      window.location.hash = redirectTo;
    } else {
      navigate(redirectTo || '/');
    }
  }, [redirectTo, navigate]);

  // Already signed in (or just signed in): return to the storefront.
  useEffect(() => {
    if (session) goBack();
  }, [session, goBack]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signIn(email, password);
      // goBack runs via the session effect once the auth state updates.
    } catch (err) {
      setError(err.message || 'Could not sign in');
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to continue shopping">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Email" type="email" value={email} onChange={setEmail} autoFocus autoComplete="email" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
        {error && <ErrorBox>{error}</ErrorBox>}
        <button type="submit" disabled={loading || !email || !password} style={primaryButton(loading || !email || !password)}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <div style={{ marginTop: 16, textAlign: 'center', fontSize: 14, color: MUTED }}>
        <a href="#/forgot-password" style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>
          Forgot password?
        </a>
      </div>
      <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${BORDER}`, textAlign: 'center', fontSize: 14, color: MUTED }}>
        New to Nova Shop?{' '}
        <Link
          to={`/register${redirectTo ? `?redirectTo=${encodeURIComponent(redirectTo)}` : ''}`}
          style={{ color: ACCENT, textDecoration: 'none', fontWeight: 700 }}
        >
          Create an account
        </Link>
      </div>
    </AuthShell>
  );
}

// -- shared auth-page primitives (duplicated in register.jsx: pages are standalone) --

function AuthShell({ title, subtitle, children }) {
  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <header style={{ background: '#fff', borderBottom: `1px solid ${BORDER}` }}>
        <div style={{ maxWidth: 1180, margin: '0 auto', padding: '14px 20px' }}>
          <a href="#/" style={{ display: 'inline-flex', alignItems: 'center', gap: 10, fontWeight: 800, fontSize: 20, color: INK, textDecoration: 'none' }}>
            <span style={{
              display: 'inline-flex', width: 32, height: 32, borderRadius: 9,
              background: `linear-gradient(135deg, ${ACCENT}, #0ea5e9)`, color: '#fff',
              alignItems: 'center', justifyContent: 'center', fontSize: 18,
            }}>🛍️</span>
            Nova Shop
          </a>
        </div>
      </header>
      <main style={{ display: 'flex', justifyContent: 'center', padding: '48px 16px' }}>
        <div style={{
          width: 'min(420px, 100%)', background: '#fff', borderRadius: 18,
          border: `1px solid ${BORDER}`, boxShadow: '0 10px 30px rgba(15,23,42,0.06)', padding: 28,
        }}>
          <h1 style={{ margin: '0 0 4px', fontSize: 24, fontWeight: 800 }}>{title}</h1>
          <p style={{ margin: '0 0 22px', color: MUTED, fontSize: 14 }}>{subtitle}</p>
          {children}
        </div>
      </main>
    </div>
  );
}

function Field({ label, type, value, onChange, autoFocus, autoComplete }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 12.5, color: MUTED, fontWeight: 600 }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        required
        style={{
          padding: '11px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
          fontSize: 14, color: INK, fontFamily: FONT,
        }}
      />
    </label>
  );
}

function ErrorBox({ children }) {
  return (
    <div style={{ color: '#b91c1c', background: '#fef2f2', padding: '10px 14px', borderRadius: 10, fontSize: 14 }}>
      {children}
    </div>
  );
}

function primaryButton(disabled) {
  return {
    marginTop: 4, padding: '13px 0', border: 'none', borderRadius: 11,
    background: disabled ? '#cbd5e1' : ACCENT, color: '#fff',
    fontWeight: 700, fontSize: 15, cursor: disabled ? 'default' : 'pointer',
  };
}
