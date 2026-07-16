def generate() -> str:
    return """// ---------------------------------------------------------------------------
// style/auth.jsx — the look & feel of the generated auth pages (signin,
// register, forgot/set/change-password, complete-profile).
//
// To rebrand ALL of them at once, place your own presentation/style/auth.jsx
// in the model (same exports, your style): files under the model's
// presentation/style/ replace the generated ones by name, while the pages
// themselves stay generated — they keep receiving generator improvements.
// For structural redesigns beyond what these primitives allow, copy the page
// you need into the model's presentation/pages/ instead.
// ---------------------------------------------------------------------------
import React from 'react';

// --- Design tokens ---
export const INK = '#1f2937';
export const MUTED = '#6b7280';
export const BORDER = '#d1d5db';
export const ACCENT = '#2563eb';
export const BG = '#f9fafb';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// Page shell: centers a titled card. Add your brand header/logo here.
export function Card({ title, subtitle, children }) {
  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG }}>
      <main style={{ display: 'flex', justifyContent: 'center', padding: '64px 16px' }}>
        <div style={{
          width: 'min(420px, 100%)', background: '#fff', borderRadius: 12,
          border: `1px solid ${BORDER}`, boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 28,
        }}>
          <h1 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 700 }}>{title}</h1>
          {subtitle && <p style={{ margin: '0 0 20px', color: MUTED, fontSize: 14 }}>{subtitle}</p>}
          {children}
        </div>
      </main>
    </div>
  );
}

export function Field({ label, name, type, value, onChange, hint, autoFocus, autoComplete }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {/* The hint lives outside the <label> so the input's accessible name is
          exactly the label text (tests and screen readers rely on it). */}
      <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <span style={{ fontSize: 13, color: MUTED, fontWeight: 600 }}>{label}</span>
        <input
          name={name}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus={autoFocus}
          autoComplete={autoComplete}
          required
          style={{
            padding: '10px 12px', borderRadius: 8, border: `1px solid ${BORDER}`,
            fontSize: 14, color: INK, fontFamily: FONT,
          }}
        />
      </label>
      {hint && <span style={{ fontSize: 12, color: MUTED }}>{hint}</span>}
    </div>
  );
}

export function Message({ kind, children }) {
  const colors = kind === 'error'
    ? { color: '#b91c1c', background: '#fef2f2' }
    : { color: '#166534', background: '#f0fdf4' };
  return (
    <div role="alert" style={{ ...colors, padding: '10px 14px', borderRadius: 8, fontSize: 14 }}>
      {children}
    </div>
  );
}

export function SubmitButton({ disabled, children }) {
  return (
    <button type="submit" disabled={disabled} style={{
      marginTop: 4, padding: '12px 0', border: 'none', borderRadius: 8,
      background: disabled ? '#cbd5e1' : ACCENT, color: '#fff',
      fontWeight: 700, fontSize: 15, cursor: disabled ? 'default' : 'pointer', fontFamily: FONT,
    }}>
      {children}
    </button>
  );
}
"""
