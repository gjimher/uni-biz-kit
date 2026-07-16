// ---------------------------------------------------------------------------
// Intranet look & feel for the generated auth pages (signin, forgot/set/
// change-password, complete-profile). Replaces the generated
// presentation/style/auth.jsx: same exports, corporate styling — the pages
// themselves stay generated and keep receiving generator improvements.
// ---------------------------------------------------------------------------
import React from 'react';

// --- Design tokens (portal palette, see pages/index.jsx) ---
export const INK = '#1e293b';
export const MUTED = '#64748b';
export const BORDER = '#e2e8f0';
export const ACCENT = '#2563eb';
export const BG = '#f8fafc';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// Page shell: centered card with the corporate brand on top.
export function Card({ title, subtitle, children }) {
  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG }}>
      <main style={{ display: 'flex', justifyContent: 'center', padding: '80px 16px' }}>
        <div style={{
          width: 'min(420px, 100%)', background: '#fff', borderRadius: 18,
          border: `1px solid ${BORDER}`, boxShadow: '0 10px 30px rgba(15,23,42,0.06)', padding: 28,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <span style={{
              display: 'inline-flex', width: 38, height: 38, borderRadius: 11,
              background: `linear-gradient(135deg, ${ACCENT}, #0ea5e9)`, color: '#fff',
              alignItems: 'center', justifyContent: 'center', fontSize: 21,
            }}>🏢</span>
            <span style={{ fontWeight: 800, fontSize: 22 }}>Intranet</span>
          </div>
          <h1 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 800 }}>{title}</h1>
          {subtitle && <p style={{ margin: '0 0 22px', color: MUTED, fontSize: 14 }}>{subtitle}</p>}
          {children}
        </div>
      </main>
    </div>
  );
}

export function Field({ label, name, type, value, onChange, hint, autoFocus, autoComplete }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {/* Hint outside the <label> so the input's accessible name is exactly the label text. */}
      <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <span style={{ fontSize: 12.5, color: MUTED, fontWeight: 600 }}>{label}</span>
        <input
          name={name}
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
      {hint && <span style={{ fontSize: 12, color: MUTED }}>{hint}</span>}
    </div>
  );
}

export function Message({ kind, children }) {
  const colors = kind === 'error'
    ? { color: '#b91c1c', background: '#fef2f2' }
    : { color: '#166534', background: '#f0fdf4' };
  return (
    <div role="alert" style={{ ...colors, padding: '10px 14px', borderRadius: 10, fontSize: 14 }}>
      {children}
    </div>
  );
}

export function SubmitButton({ disabled, children }) {
  return (
    <button type="submit" disabled={disabled} style={{
      marginTop: 4, padding: '13px 0', border: 'none', borderRadius: 11,
      background: disabled ? '#cbd5e1' : ACCENT, color: '#fff',
      fontWeight: 700, fontSize: 15, cursor: disabled ? 'default' : 'pointer', fontFamily: FONT,
    }}>
      {children}
    </button>
  );
}
