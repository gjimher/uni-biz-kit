from ._common import UI_IMPORT, header


def generate() -> str:
    return header("Change-password page") + """import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
__UI_IMPORT__
import { changePassword, useRequireSession } from '../lib';

export default function ChangePasswordPage() {
  const session = useRequireSession(); // redirects to /signin when signed out
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  if (session === undefined) return null; // session still loading

  async function handleSubmit(e) {
    e.preventDefault();
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.');
      return;
    }
    if (newPassword.length < 6) {
      setError('New password must be at least 6 characters.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await changePassword(currentPassword, newPassword);
      setSuccess(true);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title="Change password">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Current Password" type="password" value={currentPassword} onChange={setCurrentPassword}
          autoFocus autoComplete="current-password" />
        <Field label="New Password" type="password" value={newPassword} onChange={setNewPassword}
          hint="At least 6 characters" autoComplete="new-password" />
        <Field label="Confirm New Password" type="password" value={confirmPassword} onChange={setConfirmPassword}
          autoComplete="new-password" />
        {error && <Message kind="error">{error}</Message>}
        {success && <Message kind="success">Password updated successfully.</Message>}
        <SubmitButton disabled={loading || !currentPassword || !newPassword || !confirmPassword}>
          {loading ? 'Updating…' : 'Update Password'}
        </SubmitButton>
      </form>
      <div style={{ marginTop: 18, paddingTop: 14, borderTop: `1px solid ${BORDER}`, fontSize: 13 }}>
        <button type="button" onClick={() => navigate(-1)} style={{
          border: 'none', background: 'none', padding: 0, color: ACCENT,
          fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: FONT,
        }}>
          ← Back
        </button>
      </div>
    </Card>
  );
}
""".replace("__UI_IMPORT__", UI_IMPORT)
