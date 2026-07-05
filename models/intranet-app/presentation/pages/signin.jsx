import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { signIn, useSession, testUsers } from '../lib';

// ---------------------------------------------------------------------------
// Intranet sign-in page. The portal is fully private, so the home page bounces
// here when there is no session. Accounts are provisioned by the company —
// there is no self-registration link (registration.allow is false).
// ---------------------------------------------------------------------------

const ACCENT = '#2563eb';
const ACCENT_2 = '#0ea5e9';
const INK = '#1e293b';
const MUTED = '#64748b';
const BORDER = '#e2e8f0';
const BG_SOFT = '#f8fafc';
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export default function SignInPage() {
  const navigate = useNavigate();
  const session = useSession(); // undefined = loading

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // Already signed in (or just signed in): go to the portal home.
  useEffect(() => {
    if (session) navigate('/');
  }, [session, navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signIn(email, password);
      // The session effect above navigates once the auth state updates.
    } catch (err) {
      setError(err.message || 'Could not sign in');
      setLoading(false);
    }
  }

  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <main style={{ display: 'flex', justifyContent: 'center', padding: '80px 16px' }}>
        <div style={{
          width: 'min(420px, 100%)', background: '#fff', borderRadius: 18,
          border: `1px solid ${BORDER}`, boxShadow: '0 10px 30px rgba(15,23,42,0.06)', padding: 28,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <span style={{
              display: 'inline-flex', width: 38, height: 38, borderRadius: 11,
              background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`, color: '#fff',
              alignItems: 'center', justifyContent: 'center', fontSize: 21,
            }}>🏢</span>
            <span style={{ fontWeight: 800, fontSize: 22 }}>Intranet</span>
          </div>
          <h1 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 800 }}>Welcome back</h1>
          <p style={{ margin: '0 0 22px', color: MUTED, fontSize: 14 }}>
            Sign in with your corporate account
          </p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Field label="Email" type="email" value={email} onChange={setEmail} autoFocus autoComplete="email" />
            <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
            {error && (
              <div style={{ color: '#b91c1c', background: '#fef2f2', padding: '10px 14px', borderRadius: 10, fontSize: 14 }}>
                {error}
              </div>
            )}
            <button type="submit" disabled={loading || !email || !password} style={{
              marginTop: 4, padding: '13px 0', border: 'none', borderRadius: 11,
              background: (loading || !email || !password) ? '#cbd5e1' : ACCENT, color: '#fff',
              fontWeight: 700, fontSize: 15, cursor: (loading || !email || !password) ? 'default' : 'pointer',
            }}>
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <TestUserPicker onPick={(user) => { setEmail(user.email); setPassword(user.password); }} />

          <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${BORDER}`, textAlign: 'center', fontSize: 13, color: MUTED }}>
            No account? Ask HR to provision one for you.
          </div>
        </div>
      </main>
    </div>
  );
}

// Demo helper: lists the seed users from security.json so anyone can try the
// intranet without knowing the credentials. Picking one fills the form.
function TestUserPicker({ onPick }) {
  const [open, setOpen] = useState(false);
  if (testUsers.length === 0) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          width: '100%', padding: '11px 0', borderRadius: 11, border: `1px solid ${ACCENT}`,
          background: '#fff', color: ACCENT, fontWeight: 700, fontSize: 14, cursor: 'pointer', fontFamily: FONT,
        }}
      >
        {open ? 'Hide test users' : 'Fill test user…'}
      </button>
      {open && (
        <div style={{ marginTop: 8, border: `1px solid ${BORDER}`, borderRadius: 11, overflow: 'hidden' }}>
          {testUsers.map((user) => (
            <button
              key={user.email}
              type="button"
              onClick={() => { onPick(user); setOpen(false); }}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                width: '100%', padding: '10px 14px', border: 'none', borderBottom: `1px solid ${BORDER}`,
                background: BG_SOFT, cursor: 'pointer', fontFamily: FONT, fontSize: 14, color: INK, textAlign: 'left',
              }}
            >
              <span style={{ fontWeight: 600 }}>{user.email}</span>
              <span style={{ color: MUTED, fontSize: 12.5 }}>{user.roles.join(', ')}</span>
            </button>
          ))}
        </div>
      )}
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
