import React, { useCallback, useEffect, useState } from 'react';
import MDEditor from '@uiw/react-md-editor';
import { supabaseClient } from '../../../supabaseClient';
import { useSession, getProfile } from '../../lib';
import {
  PortalHeader, Card, Centered, StateBadge, Badge, formatDay,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/tickets — simple helpdesk. Employees open service requests addressed
// to HR or IT (markdown description); the handling team drives the workflow
// (open → in_progress → resolved) from the backoffice and fills `resolution`.
// owner_write RLS scopes this list to the signed-in employee's own tickets.
// ---------------------------------------------------------------------------

const TEAMS = [
  { value: 'hr', label: 'Human Resources', emoji: '🧑‍💼' },
  { value: 'it', label: 'IT / Systems', emoji: '💻' },
];
const PRIORITIES = ['low', 'normal', 'high'];
const PRIORITY_COLORS = { low: '#64748b', normal: '#0ea5e9', high: '#dc2626' };

export default function MyTickets() {
  const session = useSession();
  const [me, setMe] = useState(null);
  const [tickets, setTickets] = useState(null);
  const [expanded, setExpanded] = useState(null); // ticket id with the description open
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    const profile = await getProfile();
    const record = profile?.record ?? null;
    setMe(record);
    if (!record) { setTickets([]); return; }
    const { data } = await supabaseClient
      .from('ticket')
      .select('*')
      .eq('requester', record.id)
      .order('id', { ascending: false });
    setTickets(data ?? []);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <PortalHeader session={session} active="tickets" />

      <main style={{ maxWidth: 860, margin: '0 auto', padding: '28px 20px 80px' }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>Helpdesk</h1>
        <p style={{ margin: '6px 0 0', color: MUTED, fontSize: 14.5 }}>
          Need something from HR or IT? Open a ticket and follow it here.
        </p>

        {tickets === null ? (
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

            <NewTicketForm me={me} onCreated={refresh} onError={setError} />

            {tickets.length === 0 ? (
              <Centered>No tickets yet.</Centered>
            ) : (
              <div style={{ marginTop: 18 }}>
                {tickets.map((t) => (
                  <Card key={t.id} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 15 }}>
                          {TEAMS.find((x) => x.value === t.team)?.emoji} {t.subject}
                        </div>
                        <div style={{ color: MUTED, fontSize: 12.5, marginTop: 3 }}>
                          #{t.id} · {TEAMS.find((x) => x.value === t.team)?.label ?? t.team}
                          {t._created_at ? ` · ${formatDay(t._created_at)}` : ''}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <Badge label={t.priority} color={PRIORITY_COLORS[t.priority] ?? MUTED} />
                        <StateBadge state={t.state} />
                        <button onClick={() => setExpanded(expanded === t.id ? null : t.id)} style={{
                          border: `1px solid ${BORDER}`, background: '#fff', borderRadius: 9,
                          padding: '6px 12px', cursor: 'pointer', fontSize: 12.5, fontWeight: 700, color: INK,
                        }}>{expanded === t.id ? 'Hide' : 'Details'}</button>
                      </div>
                    </div>

                    {expanded === t.id && (
                      <div data-color-mode="light" style={{ marginTop: 12, borderTop: `1px solid ${BORDER}`, paddingTop: 12 }}>
                        <MDEditor.Markdown source={t.description ?? ''} style={{ fontSize: 14, background: 'transparent' }} />
                        {t.resolution && (
                          <div style={{
                            marginTop: 12, background: '#ecfdf5', border: '1px solid #a7f3d0',
                            borderRadius: 10, padding: '10px 14px', fontSize: 13.5,
                          }}>
                            <strong>Resolution:</strong> {t.resolution}
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ===========================================================================
// New ticket form
// ===========================================================================

function NewTicketForm({ me, onCreated, onError }) {
  const [open, setOpen] = useState(false);
  const [team, setTeam] = useState('it');
  const [priority, setPriority] = useState('normal');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  async function create(e) {
    e.preventDefault();
    setBusy(true); onError(null);
    const { error } = await supabaseClient.from('ticket').insert({
      requester: me.id, team, priority, subject, description,
    });
    if (error) onError(error.message);
    else { setOpen(false); setSubject(''); setDescription(''); }
    await onCreated();
    setBusy(false);
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{
        marginTop: 18, padding: '11px 20px', borderRadius: 11, cursor: 'pointer',
        border: `1px dashed ${ACCENT}`, background: '#eff6ff', color: ACCENT,
        fontWeight: 700, fontSize: 14, width: '100%',
      }}>+ New ticket</button>
    );
  }

  return (
    <Card style={{ marginTop: 18 }}>
      <form onSubmit={create} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <label style={fieldLabel}>
          <span style={fieldCaption}>Team</span>
          <select value={team} onChange={(e) => setTeam(e.target.value)} style={inputStyle}>
            {TEAMS.map((t) => <option key={t.value} value={t.value}>{t.emoji} {t.label}</option>)}
          </select>
        </label>
        <label style={fieldLabel}>
          <span style={fieldCaption}>Priority</span>
          <select value={priority} onChange={(e) => setPriority(e.target.value)} style={inputStyle}>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label style={{ ...fieldLabel, gridColumn: '1 / -1' }}>
          <span style={fieldCaption}>Subject</span>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} required minLength={3}
            placeholder="Short summary of what you need" style={inputStyle} />
        </label>
        <label style={{ ...fieldLabel, gridColumn: '1 / -1' }}>
          <span style={fieldCaption}>Description (markdown supported)</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} required rows={5}
            placeholder={'What do you need?\n\n* Context\n* Asset numbers, dates…'}
            style={{ ...inputStyle, resize: 'vertical' }} />
        </label>
        <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button type="button" onClick={() => setOpen(false)} style={{
            padding: '8px 16px', borderRadius: 9, cursor: 'pointer', fontSize: 13.5, fontWeight: 700,
            border: `1px solid ${BORDER}`, background: '#fff', color: INK,
          }}>Cancel</button>
          <button type="submit" disabled={busy} style={{
            padding: '8px 16px', borderRadius: 9, cursor: busy ? 'default' : 'pointer',
            fontSize: 13.5, fontWeight: 700, border: 'none',
            background: busy ? '#cbd5e1' : ACCENT, color: '#fff',
          }}>{busy ? 'Opening…' : 'Open ticket'}</button>
        </div>
      </form>
    </Card>
  );
}

const fieldLabel = { display: 'flex', flexDirection: 'column', gap: 5 };
const fieldCaption = { fontSize: 12.5, color: MUTED, fontWeight: 600 };
const inputStyle = {
  padding: '10px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
  fontSize: 14, color: INK, fontFamily: FONT, background: '#fff',
};
