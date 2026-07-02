import React, { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { signUp } from '../lib';

// ---------------------------------------------------------------------------
// Storefront registration page. Same look & feel as the shop (see index.jsx).
// The name is sent as signUp user metadata (first_name/last_name) and lands in
// the customer profile when the account is confirmed and first logs in.
// ---------------------------------------------------------------------------

const ACCENT = '#6366f1';
const INK = '#1e293b';
const MUTED = '#64748b';
const BORDER = '#e2e8f0';
const BG_SOFT = '#f8fafc';
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export default function RegisterPage() {
  const [searchParams] = useSearchParams();
  const redirectTo = searchParams.get('redirectTo') || '';

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState(false);

  const signinPath = `/signin${redirectTo ? `?redirectTo=${encodeURIComponent(redirectTo)}` : ''}`;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    setLoading(true);
    try {
      await signUp(email, password, {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });
      setRegistered(true);
    } catch (err) {
      setError(err.message || 'Could not create the account');
    } finally {
      setLoading(false);
    }
  }

  if (registered) {
    return (
      <AuthShell title="Check your email" subtitle={`We sent a confirmation link to ${email}`}>
        <div style={{
          padding: '14px 16px', borderRadius: 12, background: '#f0fdf4',
          color: '#166534', fontSize: 14, lineHeight: 1.5,
        }}>
          Click the link in the email to activate your account, then sign in to start shopping.
        </div>
        <Link to={signinPath} style={{ display: 'block', marginTop: 18, textAlign: 'center', color: ACCENT, textDecoration: 'none', fontWeight: 700, fontSize: 14 }}>
          Go to sign in
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Create your account" subtitle="Join Nova Shop — it only takes a minute">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label="First name" type="text" value={firstName} onChange={setFirstName} autoFocus autoComplete="given-name" />
          <Field label="Last name" type="text" value={lastName} onChange={setLastName} autoComplete="family-name" />
        </div>
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" />
        <Field label="Confirm password" type="password" value={confirmPassword} onChange={setConfirmPassword} autoComplete="new-password" />
        {error && <ErrorBox>{error}</ErrorBox>}
        <button
          type="submit"
          disabled={loading || !firstName.trim() || !lastName.trim() || !email || !password || !confirmPassword}
          style={primaryButton(loading || !firstName.trim() || !lastName.trim() || !email || !password || !confirmPassword)}
        >
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${BORDER}`, textAlign: 'center', fontSize: 14, color: MUTED }}>
        Already have an account?{' '}
        <Link to={signinPath} style={{ color: ACCENT, textDecoration: 'none', fontWeight: 700 }}>
          Sign in
        </Link>
      </div>
    </AuthShell>
  );
}

// -- shared auth-page primitives (duplicated in signin.jsx: pages are standalone) --

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
          width: 'min(460px, 100%)', background: '#fff', borderRadius: 18,
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
