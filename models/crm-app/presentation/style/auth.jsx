// ---------------------------------------------------------------------------
// UBK CRM look & feel for the generated auth pages (signin, forgot/set/
// change-password, complete-profile). Replaces the generated
// presentation/style/auth.jsx: same exports, product styling — the pages
// themselves stay generated and keep receiving generator improvements.
// ---------------------------------------------------------------------------
import React from 'react';

// --- Design tokens (portal palette, see pages/index.jsx) ---
export const INK = '#181818';
export const MUTED = '#5c6b7a';
export const BORDER = '#d8dde6';
export const ACCENT = '#0176d3';
export const BG = '#f3f6f9';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// Page shell: centered card with the product mark on top.
export function Card({ title, subtitle, children }) {
  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG }}>
      <main style={{ display: 'flex', justifyContent: 'center', padding: '80px 16px' }}>
        <div style={{
          width: 'min(420px, 100%)', background: '#fff', borderRadius: 12,
          border: `1px solid ${BORDER}`, boxShadow: '0 8px 24px rgba(9,30,66,0.08)', padding: 28,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <span style={{
              display: 'inline-flex', width: 38, height: 38, borderRadius: 9,
              background: `linear-gradient(135deg, ${ACCENT}, #032d60)`, color: '#fff',
              alignItems: 'center', justifyContent: 'center', fontSize: 19, fontWeight: 700,
            }}>☁</span>
            <span style={{ fontWeight: 800, fontSize: 22 }}>UBK CRM</span>
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
            padding: '11px 12px', borderRadius: 6, border: `1px solid ${BORDER}`,
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
    ? { color: '#ba0517', background: '#feded8' }
    : { color: '#2e844a', background: '#d9f5e3' };
  return (
    <div role="alert" style={{ ...colors, padding: '10px 14px', borderRadius: 6, fontSize: 14 }}>
      {children}
    </div>
  );
}

export function SubmitButton({ disabled, children }) {
  return (
    <button type="submit" disabled={disabled} style={{
      marginTop: 4, padding: '12px 0', border: 'none', borderRadius: 6,
      background: disabled ? '#c9c9c9' : ACCENT, color: '#fff',
      fontWeight: 700, fontSize: 15, cursor: disabled ? 'default' : 'pointer', fontFamily: FONT,
    }}>
      {children}
    </button>
  );
}
