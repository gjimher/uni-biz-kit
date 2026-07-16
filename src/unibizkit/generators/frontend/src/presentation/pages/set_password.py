from ._common import UI_IMPORT, header


def generate() -> str:
    return header("Set-password page (recovery-link landing)") + """import React, { useEffect, useState } from 'react';
__UI_IMPORT__
import { hasPasswordRecovery, completePasswordReset } from '../lib';

// The recovery email links back to the app, which rewrites the URL into this
// page (see supabaseClient.js). completePasswordReset() consumes whatever
// credential the link left behind (URL tokens or a live recovery session).
export default function SetPasswordPage() {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Anyone landing here without a recovery credential has nothing to work with.
  useEffect(() => {
    hasPasswordRecovery().then((ok) => {
      if (!ok) window.location.hash = '#/signin';
    });
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirm) {
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
      await completePasswordReset(password);
      // Full page load (not a SPA navigation) so the Supabase client
      // re-initialises from storage with the fresh session token. Adjust the
      // destination to your app's landing page.
      window.location.replace(import.meta.env.VITE_BASE_URI + '#/admin');
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  return (
    <Card title="Set a new password" subtitle="Choose the new password for your account">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Password" type="password" value={password} onChange={setPassword}
          hint="At least 6 characters" autoFocus autoComplete="new-password" />
        <Field label="Confirm password" type="password" value={confirm} onChange={setConfirm}
          autoComplete="new-password" />
        {error && <Message kind="error">{error}</Message>}
        <SubmitButton disabled={loading || !password || !confirm}>
          {loading ? 'Saving…' : 'Save'}
        </SubmitButton>
      </form>
    </Card>
  );
}
""".replace("__UI_IMPORT__", UI_IMPORT)
