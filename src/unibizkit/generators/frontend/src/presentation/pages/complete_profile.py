from ._common import UI_IMPORT, header


def generate() -> str:
    return header("Profile-completion page") + """import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
__UI_IMPORT__
import {
  useRequireSession, getMissingProfileFields, validateProfileFields, completeProfileFields,
} from '../lib';

// Collects the mandatory profile fields ("ask_after_login") that are still
// empty for the logged-in user. The sign-in page redirects here right after
// login when something is missing (the admin UI enforces the same gate with a
// blocking dialog) and leaves the final destination in location.state.
export default function CompleteProfilePage() {
  const session = useRequireSession(); // redirects to /signin when signed out
  const navigate = useNavigate();
  const location = useLocation();
  // Where to continue once the profile is complete.
  const target = location.state?.nextPathname || '/';

  const [gate, setGate] = useState(undefined); // undefined = loading, null = nothing missing
  const [values, setValues] = useState({});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (session) getMissingProfileFields().then(setGate);
  }, [session]);

  const goToTarget = () => {
    if (target.startsWith('#/')) {
      window.location.hash = target;
    } else {
      navigate(target);
    }
  };

  if (!session || gate === undefined) return null; // still loading

  if (gate === null) {
    return (
      <Card title="Complete your profile">
        <Message kind="success">Your profile is complete.</Message>
        <div style={{ marginTop: 16, fontSize: 13 }}>
          <Link to={target.startsWith('#/') ? '/' : target} style={{ color: ACCENT, textDecoration: 'none', fontWeight: 600 }}>Continue</Link>
        </div>
      </Card>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const validationError = validateProfileFields(gate.fields, values);
    if (validationError) {
      setError(validationError);
      return;
    }
    setSaving(true);
    setError('');
    try {
      await completeProfileFields(gate, values);
      goToTarget();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <Card title="Complete your profile" subtitle="Please fill in the following required information">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {gate.fields.map((f) => (
          <Field
            key={f.name}
            label={f.label}
            type="text"
            value={values[f.name] ?? ''}
            onChange={(v) => setValues({ ...values, [f.name]: v })}
            hint={f.description}
          />
        ))}
        {error && <Message kind="error">{error}</Message>}
        <SubmitButton disabled={saving}>Save</SubmitButton>
      </form>
    </Card>
  );
}
""".replace("__UI_IMPORT__", UI_IMPORT)
