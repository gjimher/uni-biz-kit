import React, { useCallback, useEffect, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { useSession, getProfile, transition } from '../../lib';
import {
  PortalHeader, Card, Centered, StateBadge, formatDay,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/requests — vacations and short leaves. Requests are created as drafts
// and submitted to HR through the approval workflow ("Submit" calls the
// workflow-transition edge function). The backend FEEL rules re-check the
// vacation/flex balances at submit and approve time, so over-budget requests
// fail with a readable error even if this page's meters are stale.
// ---------------------------------------------------------------------------

const LEAVE_TYPES = [
  { value: 'medical', label: 'Doctor visit' },
  { value: 'personal', label: 'Personal errand' },
  { value: 'flex', label: 'Use flexibility hours' },
];

export default function MyRequests() {
  const session = useSession();
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState('vacation'); // 'vacation' | 'leave'
  const [vacations, setVacations] = useState(null);
  const [leaves, setLeaves] = useState(null);
  const [holidays, setHolidays] = useState([]);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    const profile = await getProfile();
    const record = profile?.record ?? null;
    setMe(record);
    if (!record) { setVacations([]); setLeaves([]); return; }
    const [vac, leave] = await Promise.all([
      supabaseClient.from('vacation_request').select('*')
        .eq('employee', record.id).order('id', { ascending: false }),
      supabaseClient.from('leave_request').select('*')
        .eq('employee', record.id).order('id', { ascending: false }),
    ]);
    setVacations(vac.data ?? []);
    setLeaves(leave.data ?? []);
    if (record.work_center) {
      const { data } = await supabaseClient.from('holiday')
        .select('date, name')
        .eq('work_center', record.work_center)
        .gte('date', new Date().toISOString().slice(0, 10))
        .order('date')
        .limit(6);
      setHolidays(data ?? []);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function submitRequest(concept, id) {
    setError(null);
    try {
      await transition(concept, id, 'submitted', '');
    } catch (err) {
      setError(err.message);
    }
    await refresh();
  }

  async function deleteDraft(concept, id) {
    setError(null);
    const { error: err } = await supabaseClient.from(concept).delete().eq('id', id);
    if (err) setError(err.message);
    await refresh();
  }

  const allowance = Number(me?.vacation_days_per_year ?? 0);
  const used = Number(me?.vacation_days_used ?? 0);
  const flexBalance = Number(me?.flex_hours_earned ?? 0) - Number(me?.flex_hours_used ?? 0);

  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <PortalHeader session={session} active="requests" />

      <main style={{ maxWidth: 900, margin: '0 auto', padding: '28px 20px 80px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>My requests</h1>
          <div style={{ display: 'flex', gap: 8 }}>
            <TabButton label="🏖️ Vacations" active={tab === 'vacation'} onClick={() => setTab('vacation')} />
            <TabButton label="🕑 Leaves" active={tab === 'leave'} onClick={() => setTab('leave')} />
          </div>
        </div>

        {vacations === null ? (
          <Centered>Loading…</Centered>
        ) : !me ? (
          <Centered>No employee profile is linked to your account. Ask HR.</Centered>
        ) : (
          <>
            {error && (
              <div style={{ color: '#b91c1c', background: '#fef2f2', padding: '10px 14px', borderRadius: 10, fontSize: 14, marginTop: 14 }}>
                {error}
              </div>
            )}

            {tab === 'vacation' ? (
              <>
                <BalanceMeter used={used} total={allowance} />
                <NewVacationForm me={me} onCreated={refresh} onError={setError} />
                <RequestList
                  items={vacations}
                  emptyText="No vacation requests yet."
                  render={(r) => (
                    <>
                      <div style={{ fontWeight: 700 }}>
                        {formatDay(r.start_date)} → {formatDay(r.end_date)}
                        <span style={{ color: MUTED, fontWeight: 600 }}> · {r.days_count} day{r.days_count === 1 ? '' : 's'}</span>
                      </div>
                      {r.comment && <div style={{ color: MUTED, fontSize: 13, marginTop: 3 }}>{r.comment}</div>}
                      {r.hr_comment && <div style={{ color: '#b45309', fontSize: 13, marginTop: 3 }}>HR: {r.hr_comment}</div>}
                    </>
                  )}
                  onSubmit={(id) => submitRequest('vacation_request', id)}
                  onDelete={(id) => deleteDraft('vacation_request', id)}
                />
              </>
            ) : (
              <>
                <Card style={{ marginTop: 18, padding: '12px 16px', display: 'flex', gap: 20, flexWrap: 'wrap', fontSize: 14 }}>
                  <span><strong>Flex balance:</strong> {flexBalance >= 0 ? '+' : ''}{flexBalance.toFixed(2)} h</span>
                  <span style={{ color: MUTED }}>Medical and personal leaves are paid time; “flex” leaves spend your balance.</span>
                </Card>
                <NewLeaveForm me={me} onCreated={refresh} onError={setError} />
                <RequestList
                  items={leaves}
                  emptyText="No leave requests yet."
                  render={(r) => (
                    <>
                      <div style={{ fontWeight: 700 }}>
                        {LEAVE_TYPES.find((t) => t.value === r.type)?.label ?? r.type}
                        <span style={{ color: MUTED, fontWeight: 600 }}>
                          {' '}· {formatDay(r.start_datetime)} · {Number(r.hours).toFixed(1)} h
                        </span>
                      </div>
                      {r.reason && <div style={{ color: MUTED, fontSize: 13, marginTop: 3 }}>{r.reason}</div>}
                      {r.hr_comment && <div style={{ color: '#b45309', fontSize: 13, marginTop: 3 }}>HR: {r.hr_comment}</div>}
                    </>
                  )}
                  onSubmit={(id) => submitRequest('leave_request', id)}
                  onDelete={(id) => deleteDraft('leave_request', id)}
                />
              </>
            )}

            {holidays.length > 0 && (
              <>
                <h2 style={{ fontSize: 16, fontWeight: 800, margin: '30px 0 8px' }}>
                  Upcoming holidays at your center
                </h2>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {holidays.map((h) => (
                    <span key={h.date} style={{
                      background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 999,
                      padding: '6px 14px', fontSize: 13,
                    }}>
                      <strong>{formatDay(h.date)}</strong> — {h.name}
                    </span>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ===========================================================================
// Vacation balance meter
// ===========================================================================

function BalanceMeter({ used, total }) {
  const left = Math.max(total - used, 0);
  const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  return (
    <Card style={{ marginTop: 18, padding: '14px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, fontWeight: 600 }}>
        <span>{left} day{left === 1 ? '' : 's'} left</span>
        <span style={{ color: MUTED }}>{used} of {total} used</span>
      </div>
      <div style={{ marginTop: 8, height: 10, borderRadius: 999, background: '#e2e8f0', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: `linear-gradient(90deg, ${ACCENT}, #0ea5e9)` }} />
      </div>
    </Card>
  );
}

// ===========================================================================
// Creation forms — new rows start in 'draft' (the workflow's initial state)
// ===========================================================================

function NewVacationForm({ me, onCreated, onError }) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [days, setDays] = useState('');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  async function create(e) {
    e.preventDefault();
    setBusy(true); onError(null);
    const { error } = await supabaseClient.from('vacation_request').insert({
      employee: me.id, start_date: start, end_date: end,
      days_count: Number(days), comment: comment || null,
    });
    if (error) onError(error.message);
    else { setOpen(false); setStart(''); setEnd(''); setDays(''); setComment(''); }
    await onCreated();
    setBusy(false);
  }

  if (!open) return <NewButton label="+ New vacation request" onClick={() => setOpen(true)} />;
  return (
    <Card style={{ marginTop: 14 }}>
      <form onSubmit={create} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <Field label="First day" type="date" value={start} onChange={setStart} required />
        <Field label="Last day" type="date" value={end} onChange={setEnd} required />
        <Field label="Working days" type="number" value={days} onChange={setDays} required min="1"
          hint="Excluding weekends & holidays" />
        <Field label="Comment (optional)" type="text" value={comment} onChange={setComment} span />
        <FormButtons busy={busy} onCancel={() => setOpen(false)} />
      </form>
    </Card>
  );
}

function NewLeaveForm({ me, onCreated, onError }) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState('medical');
  const [start, setStart] = useState('');
  const [hours, setHours] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  async function create(e) {
    e.preventDefault();
    setBusy(true); onError(null);
    const { error } = await supabaseClient.from('leave_request').insert({
      employee: me.id, type, start_datetime: new Date(start).toISOString(),
      hours: Number(hours), reason: reason || null,
    });
    if (error) onError(error.message);
    else { setOpen(false); setStart(''); setHours(''); setReason(''); }
    await onCreated();
    setBusy(false);
  }

  if (!open) return <NewButton label="+ New leave request" onClick={() => setOpen(true)} />;
  return (
    <Card style={{ marginTop: 14 }}>
      <form onSubmit={create} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <label style={fieldLabel}>
          <span style={fieldCaption}>Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)} style={inputStyle}>
            {LEAVE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <Field label="Starts at" type="datetime-local" value={start} onChange={setStart} required />
        <Field label="Hours" type="number" value={hours} onChange={setHours} required min="0.5" step="0.5" />
        <Field label="Reason (optional)" type="text" value={reason} onChange={setReason} span />
        <FormButtons busy={busy} onCancel={() => setOpen(false)} />
      </form>
    </Card>
  );
}

// ===========================================================================
// Request list with workflow actions
// ===========================================================================

function RequestList({ items, emptyText, render, onSubmit, onDelete }) {
  if (items.length === 0) return <Centered>{emptyText}</Centered>;
  return (
    <div style={{ marginTop: 16 }}>
      {items.map((r) => (
        <Card key={r.id} style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ minWidth: 0 }}>{render(r)}</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <StateBadge state={r.state} />
            {r.state === 'draft' && (
              <>
                <SmallButton label="Submit" primary onClick={() => onSubmit(r.id)} />
                <SmallButton label="Delete" onClick={() => onDelete(r.id)} />
              </>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

// ===========================================================================
// Form primitives
// ===========================================================================

const fieldLabel = { display: 'flex', flexDirection: 'column', gap: 5 };
const fieldCaption = { fontSize: 12.5, color: MUTED, fontWeight: 600 };
const inputStyle = {
  padding: '10px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
  fontSize: 14, color: INK, fontFamily: FONT, background: '#fff',
};

function Field({ label, type, value, onChange, required, min, step, hint, span }) {
  return (
    <label style={{ ...fieldLabel, gridColumn: span ? '1 / -1' : undefined }}>
      <span style={fieldCaption}>{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
        required={required} min={min} step={step} style={inputStyle} />
      {hint && <span style={{ fontSize: 11.5, color: MUTED }}>{hint}</span>}
    </label>
  );
}

function FormButtons({ busy, onCancel }) {
  return (
    <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
      <SmallButton label="Cancel" onClick={onCancel} type="button" />
      <SmallButton label={busy ? 'Saving…' : 'Save draft'} primary type="submit" disabled={busy} />
    </div>
  );
}

function SmallButton({ label, onClick, primary, type = 'button', disabled }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={{
      padding: '8px 16px', borderRadius: 9, cursor: disabled ? 'default' : 'pointer',
      fontSize: 13.5, fontWeight: 700,
      border: primary ? 'none' : `1px solid ${BORDER}`,
      background: disabled ? '#cbd5e1' : primary ? ACCENT : '#fff',
      color: primary ? '#fff' : INK,
    }}>{label}</button>
  );
}

function NewButton({ label, onClick }) {
  return (
    <button onClick={onClick} style={{
      marginTop: 14, padding: '11px 20px', borderRadius: 11, cursor: 'pointer',
      border: `1px dashed ${ACCENT}`, background: '#eff6ff', color: ACCENT,
      fontWeight: 700, fontSize: 14, width: '100%',
    }}>{label}</button>
  );
}

function TabButton({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 14, fontWeight: 600,
      border: `1px solid ${active ? ACCENT : BORDER}`,
      background: active ? ACCENT : '#fff', color: active ? '#fff' : INK,
    }}>{label}</button>
  );
}
