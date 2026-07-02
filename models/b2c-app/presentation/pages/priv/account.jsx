import React, { useCallback, useEffect, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { getProfile, updateProfile, validateRecord } from '../../lib';
import {
  ACCENT, INK, MUTED, BORDER, BG_SOFT, FONT,
  ComboField, Field, addressComboProps, setAddressField, clearAddressField,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/account — the signed-in shopper's profile (customer row) and saved
// addresses. RLS scopes both tables to the current customer, so plain selects
// and writes only ever touch the shopper's own rows.
// ---------------------------------------------------------------------------

const EMPTY_ADDRESS = {
  label: '', first_name: '', last_name: '', company: '',
  street_line_1: '', street_line_2: '', city: '', state_province: '',
  postal_code: '', country: '', is_default_shipping: false, is_default_billing: false,
};
const ADDRESS_REQUIRED = ['label', 'first_name', 'last_name', 'street_line_1', 'city', 'state_province', 'postal_code', 'country'];

// DB rows use null for empty optional columns; controlled inputs want ''.
function toAddressForm(address) {
  const form = { id: address.id };
  for (const [key, empty] of Object.entries(EMPTY_ADDRESS)) {
    form[key] = address[key] ?? empty;
  }
  return form;
}

export default function MyAccount() {
  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <div style={{ maxWidth: 860, margin: '0 auto', padding: '28px 20px 60px' }}>
        <a href="#/" style={{ textDecoration: 'none', color: MUTED, fontSize: 14, fontWeight: 600 }}>
          ← Back to shop
        </a>
        <h1 style={{ fontSize: 26, margin: '18px 0 22px' }}>My profile</h1>
        <ProfileCard />
        <AddressesCard />
      </div>
    </div>
  );
}

// --- Profile (customer row) -------------------------------------------------

function ProfileCard() {
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({ first_name: '', last_name: '', phone: '', accepts_marketing: false });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null); // { ok, text }

  useEffect(() => {
    getProfile().then((p) => {
      if (!p) return;
      setProfile(p.record);
      setForm({
        first_name: p.record.first_name ?? '',
        last_name: p.record.last_name ?? '',
        phone: p.record.phone ?? '',
        accepts_marketing: !!p.record.accepts_marketing,
      });
    });
  }, []);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const valid = form.first_name.trim() && form.last_name.trim();

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateProfile({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim() || null,
        accepts_marketing: form.accepts_marketing,
      });
      setProfile(updated);
      setMessage({ ok: true, text: 'Profile saved.' });
    } catch (err) {
      setMessage({ ok: false, text: err.message });
    }
    setSaving(false);
  }

  if (!profile) return <Card><p style={{ color: MUTED, margin: 0 }}>Loading…</p></Card>;

  return (
    <Card>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="First name *" value={form.first_name} onChange={set('first_name')} />
        <Field label="Last name *" value={form.last_name} onChange={set('last_name')} />
        <Field label="Phone" value={form.phone} onChange={set('phone')} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ fontSize: 12.5, color: MUTED, fontWeight: 600 }}>Email</span>
          <div style={{ padding: '10px 12px', borderRadius: 10, border: `1px solid ${BORDER}`, fontSize: 14, color: MUTED, background: BG_SOFT }}>
            {profile.email}
          </div>
        </div>
        <Checkbox label="I want to receive offers and news by email"
          checked={form.accepts_marketing}
          onChange={(v) => setForm((f) => ({ ...f, accepts_marketing: v }))} span />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
        <PrimaryButton onClick={save} disabled={!valid || saving}>
          {saving ? 'Saving…' : 'Save profile'}
        </PrimaryButton>
        {message && <span style={{ fontSize: 13, color: message.ok ? '#10b981' : '#dc2626' }}>{message.text}</span>}
      </div>
    </Card>
  );
}

// --- Saved addresses ----------------------------------------------------------

function AddressesCard() {
  const [customerId, setCustomerId] = useState(null);
  const [addresses, setAddresses] = useState(null); // null = loading
  const [editing, setEditing] = useState(null); // null | { id?, ...EMPTY_ADDRESS }
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null); // address id

  const reload = useCallback(() => {
    supabaseClient.from('address').select('*').order('label')
      .then(({ data }) => setAddresses(data ?? []));
  }, []);

  useEffect(() => {
    getProfile().then((p) => setCustomerId(p?.record.id ?? null));
    reload();
  }, [reload]);

  const setAddr = (col) => (value) => setEditing((f) => setAddressField(f, col, value));
  const clearAddr = (col) => () => setEditing((f) => clearAddressField(f, col));
  const set = (k) => (e) => setEditing((f) => ({ ...f, [k]: e.target.value }));

  const addrValid = editing
    && ADDRESS_REQUIRED.every((k) => String(editing[k] ?? '').trim())
    && Object.keys(validateRecord('address', editing)).length === 0;

  async function save() {
    if (!addrValid || !customerId) return;
    setSaving(true);
    setError(null);
    const row = {
      customer: customerId,
      label: editing.label.trim(),
      first_name: editing.first_name,
      last_name: editing.last_name,
      company: editing.company || null,
      street_line_1: editing.street_line_1,
      street_line_2: editing.street_line_2 || null,
      city: editing.city,
      state_province: editing.state_province,
      postal_code: editing.postal_code,
      country: editing.country,
      is_default_shipping: !!editing.is_default_shipping,
      is_default_billing: !!editing.is_default_billing,
    };
    const query = editing.id
      ? supabaseClient.from('address').update(row).eq('id', editing.id)
      : supabaseClient.from('address').insert(row);
    const { error: err } = await query;
    setSaving(false);
    if (err) { setError(err.message); return; }
    setEditing(null);
    reload();
  }

  async function remove(id) {
    setError(null);
    const { error: err } = await supabaseClient.from('address').delete().eq('id', id);
    if (err) { setError(err.message); return; }
    setConfirmDelete(null);
    reload();
  }

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>Saved addresses</h2>
        {!editing && (
          <PrimaryButton onClick={() => { setError(null); setEditing({ ...EMPTY_ADDRESS }); }}>
            Add address
          </PrimaryButton>
        )}
      </div>

      {addresses === null && <p style={{ color: MUTED, margin: 0 }}>Loading…</p>}
      {addresses?.length === 0 && !editing && (
        <p style={{ color: MUTED, margin: 0 }}>No saved addresses yet.</p>
      )}

      {addresses?.map((address) => (
        <div key={address.id} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
          padding: '12px 0', borderTop: `1px solid ${BORDER}`, flexWrap: 'wrap',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>
              {address.label}
              {address.is_default_shipping && <Tag>default shipping</Tag>}
              {address.is_default_billing && <Tag>default billing</Tag>}
            </div>
            <div style={{ color: MUTED, fontSize: 13 }}>
              {address.first_name} {address.last_name} · {address.street_line_1}
              {address.street_line_2 ? `, ${address.street_line_2}` : ''} · {address.city}, {address.state_province}, {address.postal_code}, {address.country}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <LinkButton onClick={() => { setError(null); setConfirmDelete(null); setEditing(toAddressForm(address)); }}>Edit</LinkButton>
            {confirmDelete === address.id ? (
              <>
                <LinkButton onClick={() => remove(address.id)} color="#dc2626">Confirm delete</LinkButton>
                <LinkButton onClick={() => setConfirmDelete(null)}>Cancel</LinkButton>
              </>
            ) : (
              <LinkButton onClick={() => setConfirmDelete(address.id)} color="#dc2626">Delete</LinkButton>
            )}
          </div>
        </div>
      ))}

      {editing && (
        <div style={{ borderTop: `1px solid ${BORDER}`, marginTop: 4, paddingTop: 16 }}>
          <h3 style={{ fontSize: 15, margin: '0 0 12px' }}>{editing.id ? 'Edit address' : 'New address'}</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Label * (e.g. Home, Office)" value={editing.label} onChange={set('label')} span />
            <Field label="First name *" value={editing.first_name} onChange={set('first_name')} />
            <Field label="Last name *" value={editing.last_name} onChange={set('last_name')} />
            <Field label="Company" value={editing.company} onChange={set('company')} span />
            <Field label="Street *" value={editing.street_line_1} onChange={set('street_line_1')} span />
            <Field label="Street line 2" value={editing.street_line_2} onChange={set('street_line_2')} span />
            <ComboField label="City *" value={editing.city} onChange={setAddr('city')} onClear={clearAddr('city')} {...addressComboProps('city', editing)} />
            <ComboField label="State / Province *" value={editing.state_province} onChange={setAddr('state_province')} onClear={clearAddr('state_province')} {...addressComboProps('state_province', editing)} />
            <Field label="Postal code *" value={editing.postal_code} onChange={set('postal_code')} />
            <ComboField label="Country *" value={editing.country} onChange={setAddr('country')} onClear={clearAddr('country')} {...addressComboProps('country', editing)} />
            <Checkbox label="Default shipping address" checked={!!editing.is_default_shipping}
              onChange={(v) => setEditing((f) => ({ ...f, is_default_shipping: v }))} />
            <Checkbox label="Default billing address" checked={!!editing.is_default_billing}
              onChange={(v) => setEditing((f) => ({ ...f, is_default_billing: v }))} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
            <PrimaryButton onClick={save} disabled={!addrValid || saving}>
              {saving ? 'Saving…' : 'Save address'}
            </PrimaryButton>
            <LinkButton onClick={() => setEditing(null)}>Cancel</LinkButton>
          </div>
        </div>
      )}

      {error && <p style={{ color: '#dc2626', fontSize: 13, marginTop: 12 }}>{error}</p>}
    </Card>
  );
}

// --- Small shared bits --------------------------------------------------------

function Card({ children }) {
  return (
    <div style={{
      background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 14,
      padding: '20px 22px', marginBottom: 20,
    }}>{children}</div>
  );
}

function Checkbox({ label, checked, onChange, span }) {
  return (
    <label style={{
      display: 'flex', alignItems: 'center', gap: 8, fontSize: 14,
      gridColumn: span ? '1 / -1' : 'auto', cursor: 'pointer',
    }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function PrimaryButton({ children, onClick, disabled }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={{
      background: disabled ? '#c7d2fe' : ACCENT, color: '#fff', border: 'none',
      borderRadius: 9, padding: '9px 18px', fontSize: 14, fontWeight: 700,
      cursor: disabled ? 'default' : 'pointer', fontFamily: FONT,
    }}>{children}</button>
  );
}

function LinkButton({ children, onClick, color }) {
  return (
    <button type="button" onClick={onClick} style={{
      background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
      color: color ?? INK, fontSize: 13, fontWeight: 700, fontFamily: FONT,
    }}>{children}</button>
  );
}

function Tag({ children }) {
  return (
    <span style={{
      background: `${ACCENT}1a`, color: ACCENT, borderRadius: 999,
      padding: '2px 8px', fontSize: 11, fontWeight: 700, marginLeft: 8,
    }}>{children}</span>
  );
}
