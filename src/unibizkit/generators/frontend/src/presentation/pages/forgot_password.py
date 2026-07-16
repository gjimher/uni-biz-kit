from ._common import UI_IMPORT, header


def generate() -> str:
    return header("Forgot-password page") + """import React, { useState } from 'react';
import { Link } from 'react-router-dom';
__UI_IMPORT__
import { requestPasswordReset } from '../lib';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title="Forgot password?" subtitle="We will email you a password reset link">
      {sent ? (
        <Message kind="success">
          Check your email for the password reset link.
        </Message>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Email" type="email" value={email} onChange={setEmail} autoFocus autoComplete="email" />
          {error && <Message kind="error">{error}</Message>}
          <SubmitButton disabled={loading || !email}>
            {loading ? 'Sending…' : 'Reset password'}
          </SubmitButton>
        </form>
      )}
      <div style={{ marginTop: 18, paddingTop: 14, borderTop: `1px solid ${BORDER}`, fontSize: 13 }}>
        <Link to="/signin" style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>Back to sign in</Link>
      </div>
    </Card>
  );
}
""".replace("__UI_IMPORT__", UI_IMPORT)
