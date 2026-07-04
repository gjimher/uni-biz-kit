import React, { useCallback, useEffect, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { useSession, getProfile } from '../../lib';
import {
  PortalHeader, Card, Centered, formatDay, formatTime,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/time — working-time tracking (registro de jornada). One work_log row
// per day: "Clock in" inserts it, "Clock out" completes it. worked_hours and
// overtime_hours are computed in the database; overtime accumulates into the
// employee's flexibility balance (spend it via a 'flex' leave request).
// ---------------------------------------------------------------------------

export default function MyTime() {
  const session = useSession();
  const [me, setMe] = useState(null);
  const [logs, setLogs] = useState(null); // recent logs, newest first
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const profile = await getProfile();
    const record = profile?.record ?? null;
    setMe(record);
    if (!record) { setLogs([]); return; }
    const { data } = await supabaseClient
      .from('work_log')
      .select('*')
      .eq('employee', record.id)
      .order('work_date', { ascending: false })
      .limit(14);
    setLogs(data ?? []);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const today = new Date().toISOString().slice(0, 10);
  const todayLog = (logs ?? []).find((l) => l.work_date === today);
  const clockedIn = todayLog && !todayLog.check_out;

  async function clockIn() {
    setBusy(true); setError(null);
    const { error: err } = await supabaseClient.from('work_log').insert({
      employee: me.id, work_date: today, check_in: new Date().toISOString(),
    });
    if (err) setError(err.message);
    await refresh();
    setBusy(false);
  }

  async function clockOut() {
    setBusy(true); setError(null);
    const { error: err } = await supabaseClient
      .from('work_log')
      .update({ check_out: new Date().toISOString() })
      .eq('id', todayLog.id);
    if (err) setError(err.message);
    await refresh(); // reloads the profile so the flex balance reflects the new overtime
    setBusy(false);
  }

  const flexEarned = Number(me?.flex_hours_earned ?? 0);
  const flexUsed = Number(me?.flex_hours_used ?? 0);

  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <PortalHeader session={session} active="time" />

      <main style={{ maxWidth: 860, margin: '0 auto', padding: '28px 20px 80px' }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>My time</h1>

        {logs === null ? (
          <Centered>Loading…</Centered>
        ) : !me ? (
          <Centered>No employee profile is linked to your account. Ask HR.</Centered>
        ) : (
          <>
            {/* Today card */}
            <Card style={{ marginTop: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
              <div>
                <div style={{ color: MUTED, fontSize: 13, fontWeight: 600 }}>{formatDay(today)}</div>
                <div style={{ fontSize: 22, fontWeight: 800, marginTop: 4 }}>
                  {clockedIn
                    ? `Clocked in since ${formatTime(todayLog.check_in)}`
                    : todayLog
                      ? `Done for today — ${Number(todayLog.worked_hours).toFixed(2)} h worked`
                      : 'Not clocked in yet'}
                </div>
                <div style={{ color: MUTED, fontSize: 13, marginTop: 4 }}>
                  Expected: {Number(me.daily_hours).toFixed(2)} h/day
                </div>
              </div>
              {clockedIn ? (
                <BigButton label={busy ? '…' : '⏹ Clock out'} onClick={clockOut} disabled={busy} color="#dc2626" />
              ) : !todayLog ? (
                <BigButton label={busy ? '…' : '▶ Clock in'} onClick={clockIn} disabled={busy} color={ACCENT} />
              ) : null}
            </Card>
            {error && (
              <div style={{ color: '#b91c1c', background: '#fef2f2', padding: '10px 14px', borderRadius: 10, fontSize: 14, marginTop: 10 }}>
                {error}
              </div>
            )}

            {/* Flexibility balance */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 14, marginTop: 16,
            }}>
              <MiniStat label="Flex earned" value={`${flexEarned >= 0 ? '+' : ''}${flexEarned.toFixed(2)} h`} />
              <MiniStat label="Flex spent" value={`${flexUsed.toFixed(2)} h`} />
              <MiniStat label="Balance" value={`${(flexEarned - flexUsed) >= 0 ? '+' : ''}${(flexEarned - flexUsed).toFixed(2)} h`} strong />
            </div>
            <p style={{ color: MUTED, fontSize: 13, marginTop: 8 }}>
              Hours worked above your daily hours accumulate here. Spend them with a{' '}
              <a href="#/priv/requests" style={{ color: ACCENT, fontWeight: 600 }}>flex leave request</a>.
            </p>

            {/* Recent days */}
            <h2 style={{ fontSize: 18, fontWeight: 800, margin: '26px 0 10px' }}>Recent days</h2>
            {logs.length === 0 ? (
              <Centered>No clockings yet — hit “Clock in” to start.</Centered>
            ) : (
              <Card style={{ padding: 0, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9', color: MUTED, fontSize: 12.5, textAlign: 'left' }}>
                      <th style={th}>Date</th>
                      <th style={th}>In</th>
                      <th style={th}>Out</th>
                      <th style={{ ...th, textAlign: 'right' }}>Worked</th>
                      <th style={{ ...th, textAlign: 'right' }}>Overtime</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((l) => (
                      <tr key={l.id} style={{ borderTop: `1px solid ${BORDER}` }}>
                        <td style={td}>{formatDay(l.work_date)}</td>
                        <td style={td}>{formatTime(l.check_in)}</td>
                        <td style={td}>{l.check_out ? formatTime(l.check_out) : <em style={{ color: ACCENT }}>working…</em>}</td>
                        <td style={{ ...td, textAlign: 'right' }}>
                          {l.worked_hours == null ? '—' : `${Number(l.worked_hours).toFixed(2)} h`}
                        </td>
                        <td style={{
                          ...td, textAlign: 'right', fontWeight: 600,
                          color: Number(l.overtime_hours) > 0 ? '#10b981' : Number(l.overtime_hours) < 0 ? '#dc2626' : MUTED,
                        }}>
                          {l.check_out ? `${Number(l.overtime_hours) >= 0 ? '+' : ''}${Number(l.overtime_hours).toFixed(2)} h` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </>
        )}
      </main>
    </div>
  );
}

const th = { padding: '10px 16px', fontWeight: 700 };
const td = { padding: '10px 16px' };

function BigButton({ label, onClick, disabled, color }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: '16px 30px', borderRadius: 14, border: 'none', cursor: disabled ? 'default' : 'pointer',
      background: disabled ? '#cbd5e1' : color, color: '#fff', fontWeight: 800, fontSize: 17,
      boxShadow: '0 8px 22px rgba(15,23,42,0.15)',
    }}>{label}</button>
  );
}

function MiniStat({ label, value, strong }) {
  return (
    <Card style={{ padding: '12px 16px' }}>
      <div style={{ color: MUTED, fontSize: 12.5, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: strong ? 800 : 700, marginTop: 2 }}>{value}</div>
    </Card>
  );
}
