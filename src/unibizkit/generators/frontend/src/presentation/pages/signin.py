from ....context import Context
from ._common import UI_IMPORT, header


def generate(ctx: Context) -> str:
    sso_enabled = ctx.security_config["sso"]["enabled"]
    allow_registration = ctx.security_config["registration"]["allow"]

    lib_imports = "signIn, useSession, testUsers"
    if sso_enabled:
        lib_imports += ", signInWithSso"

    sso_handler = """
  async function handleSso() {
    setError('');
    try {
      await signInWithSso(redirectTo); // redirects the browser away on success
    } catch (err) {
      setError(err.message || 'SSO login failed');
    }
  }
""" if sso_enabled else ""

    sso_button = """
      <div style={{ marginTop: 14 }}>
        <button type="button" onClick={handleSso} style={{
          width: '100%', padding: '11px 0', borderRadius: 8, border: `1px solid ${ACCENT}`,
          background: '#fff', color: ACCENT, fontWeight: 700, fontSize: 14, cursor: 'pointer', fontFamily: FONT,
        }}>
          Login with SSO
        </button>
      </div>
""" if sso_enabled else ""

    register_link = (
        """        <Link to={registerPath} style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>Create an account</Link>"""
        if allow_registration else
        """        <span style={{ color: MUTED }}>No account? Contact your administrator.</span>"""
    )
    register_path = (
        """  const registerPath = `/register${searchParams.get('redirectTo') ? `?redirectTo=${encodeURIComponent(searchParams.get('redirectTo'))}` : ''}`;
""" if allow_registration else "")

    return header("Sign-in page") + """import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { __LIB_IMPORTS__ } from '../lib';
__UI_IMPORT__

// This page is also the app's /login route (react-admin's authProvider
// redirects here when the backoffice is visited without a session).
export default function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const session = useSession(); // undefined = loading, null = signed out

  // Where to go after signing in: react-admin leaves the page it bounced from
  // in location.state (nextPathname); custom flows can pass ?redirectTo=<path>.
  const redirectTo = location.state?.nextPathname
    ? location.state.nextPathname + (location.state.nextSearch || '')
    : (searchParams.get('redirectTo') || '/');
__REGISTER_PATH__
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const goTo = (target) => {
    if (target.startsWith('#/')) {
      window.location.hash = target;
    } else {
      navigate(target);
    }
  };

  // Already signed in (or just signed in): continue to the intended page.
  // (Mandatory profile fields are handled globally: the router's profile gate
  // intercepts any fresh session that still has "ask_after_login" fields.)
  // Depends only on `session` on purpose: the redirect target must be the one
  // captured when the session appeared.
  useEffect(() => {
    if (!session) return;
    goTo(redirectTo);
  }, [session]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signIn(email, password);
      // The session effect above navigates once the auth state updates.
    } catch (err) {
      setError(err.message || 'Could not sign in');
      setLoading(false);
    }
  }
__SSO_HANDLER__
  return (
    <Card title="Sign in" subtitle="Welcome back">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Email" name="email" type="email" value={email} onChange={setEmail} autoFocus autoComplete="email" />
        <Field label="Password" name="password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
        {error && <Message kind="error">{error}</Message>}
        <SubmitButton disabled={loading || !email || !password}>
          {loading ? 'Signing in…' : 'Sign in'}
        </SubmitButton>
      </form>
__SSO_BUTTON__
      <TestUserPicker onPick={(user) => { setEmail(user.email); setPassword(user.password); }} />
      <div style={{
        marginTop: 18, paddingTop: 14, borderTop: `1px solid ${BORDER}`,
        display: 'flex', justifyContent: 'space-between', fontSize: 13,
      }}>
        <Link to="/forgot-password" style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>Forgot password?</Link>
__REGISTER_LINK__
      </div>
    </Card>
  );
}

// Demo helper: lists the seed users from security.json so anyone can try the
// app without knowing the credentials. Picking one fills the form.
function TestUserPicker({ onPick }) {
  const [open, setOpen] = useState(false);
  if (testUsers.length === 0) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          width: '100%', padding: '10px 0', borderRadius: 8, border: `1px solid ${BORDER}`,
          background: '#fff', color: MUTED, fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: FONT,
        }}
      >
        {open ? 'Hide test users' : 'Fill test user…'}
      </button>
      {open && (
        <div style={{ marginTop: 8, border: `1px solid ${BORDER}`, borderRadius: 8, overflow: 'hidden' }}>
          {testUsers.map((user) => (
            <button
              key={user.email}
              type="button"
              onClick={() => { onPick(user); setOpen(false); }}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                width: '100%', padding: '9px 12px', border: 'none', borderBottom: `1px solid ${BORDER}`,
                background: BG, cursor: 'pointer', fontFamily: FONT, fontSize: 13, color: INK, textAlign: 'left',
              }}
            >
              <span style={{ fontWeight: 600 }}>{user.email}</span>
              <span style={{ color: MUTED, fontSize: 12 }}>{user.roles.join(', ')}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
""".replace("__LIB_IMPORTS__", lib_imports) \
   .replace("__UI_IMPORT__", UI_IMPORT) \
   .replace("__REGISTER_PATH__", register_path) \
   .replace("__SSO_HANDLER__", sso_handler) \
   .replace("__SSO_BUTTON__", sso_button) \
   .replace("__REGISTER_LINK__", register_link)
