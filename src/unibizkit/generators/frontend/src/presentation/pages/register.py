from ._common import UI_IMPORT, header


def generate() -> str:
    return header("Registration page") + """import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { signUp } from '../lib';
__UI_IMPORT__

// Deliberately minimal (email + password): mandatory profile fields declared
// as "ask_after_login" are collected once, right after the first login — the
// same gate that covers seeded and SSO accounts, which never see this form.
export default function RegisterPage() {
  const [searchParams] = useSearchParams();
  // Keep the post-login destination across the register <-> signin hops.
  const redirectTo = searchParams.get('redirectTo') || '';
  const signinPath = `/signin${redirectTo ? `?redirectTo=${encodeURIComponent(redirectTo)}` : ''}`;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    setError('');
    setLoading(true);
    try {
      // A third argument (e.g. { first_name }) becomes Supabase user metadata
      // and prefills profile fields with a from_metadata(...) default.
      await signUp(email, password);
      setRegistered(true);
    } catch (err) {
      setError(err.message || 'Could not create the account');
      setLoading(false);
    }
  }

  if (registered) {
    return (
      <Card title="Registration successful!">
        <Message kind="success">
          Please check your email and click the confirmation link before signing in.
        </Message>
        <div style={{ marginTop: 16, fontSize: 13 }}>
          <Link to={signinPath} style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>Back to sign in</Link>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Create an account" subtitle="Register with your email and a password">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Email" name="email" type="email" value={email} onChange={setEmail} autoFocus autoComplete="email" />
        <Field label="Password" name="password" type="password" value={password} onChange={setPassword}
          hint="At least 6 characters" autoComplete="new-password" />
        <Field label="Confirm Password" name="confirmPassword" type="password" value={confirmPassword} onChange={setConfirmPassword}
          autoComplete="new-password" />
        {error && <Message kind="error">{error}</Message>}
        <SubmitButton disabled={loading || !email || !password || !confirmPassword}>
          {loading ? 'Registering…' : 'Register'}
        </SubmitButton>
      </form>
      <div style={{
        marginTop: 18, paddingTop: 14, borderTop: `1px solid ${BORDER}`,
        fontSize: 13, color: MUTED,
      }}>
        Already have an account?{' '}
        <Link to={signinPath} style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>Sign in</Link>
      </div>
    </Card>
  );
}
""".replace("__UI_IMPORT__", UI_IMPORT)
