import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { useRequireSession, getPermissions, transition, formatDate } from '../../lib';
import {
  Nav, Card, SectionTitle, ProgressBar,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, SURFACE, WON, LOST, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/service — the console a support engineer and a dispatcher share.
//
// The SLA queue is read from the `sla_report` view concept, so the "already
// late" decision is made in SQL with CURRENT_TIMESTAMP (a generated column
// cannot call now()) and every caller only sees the cases their row-level
// security allows. Dispatching a job goes through the same workflow-transition
// function the backoffice uses, so the model's guards apply here too: a job
// with no appointment refuses to leave 'new'.
// ---------------------------------------------------------------------------

const WORK_ORDER_STATES = ['new', 'dispatched', 'in_progress', 'completed'];
const STATE_LABELS = { new: 'New', dispatched: 'Dispatched', in_progress: 'In progress', completed: 'Completed' };
const PRIORITY_COLORS = { low: '#8b9bab', medium: '#5c6b7a', high: '#dd7a01', critical: '#ba0517' };

export default function ServiceConsole() {
  const session = useRequireSession();
  const [sla, setSla] = useState(null);
  const [workOrders, setWorkOrders] = useState(null);
  const [appointments, setAppointments] = useState([]);
  const [articles, setArticles] = useState([]);
  const [search, setSearch] = useState('');
  const [canDispatch, setCanDispatch] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!session) return;
    getPermissions().then((permissions) => setCanDispatch(
      (permissions?.work_order ?? []).includes('write') || (permissions?.['*'] ?? []).includes('write'),
    ));
    supabaseClient
      .from('knowledge_article')
      .select('id, title, summary, status, category(id, name), view_count, helpful_count')
      .eq('status', 'published')
      .order('view_count', { ascending: false })
      .then(({ data }) => setArticles(data ?? []));
  }, [session]);

  const load = useCallback(() => {
    supabaseClient
      .from('sla_report')
      .select('*')
      .order('hours_left')
      .then(({ data, error: loadError }) => {
        if (loadError) setError(loadError.message);
        setSla(data ?? []);
      });
    supabaseClient
      .from('work_order')
      .select('id, id_presentation, subject, state, priority, scheduled_start, duration_hours, line_total, appointment_count, account(id, name), contact(id, first_name, last_name), work_type(id, name), territory(id, name)')
      .neq('state', 'completed')
      .order('scheduled_start')
      .then(({ data }) => setWorkOrders(data ?? []));
    supabaseClient
      .from('service_appointment')
      .select('id, status, scheduled_start, scheduled_end, work_order, service_resource(id, name)')
      .order('scheduled_start')
      .then(({ data }) => setAppointments(data ?? []));
  }, []);

  useEffect(() => { load(); }, [load]);

  const breached = (sla ?? []).filter((row) => row.is_breached);
  // Still running (not met, not breached) and inside the last eight hours of its window:
  // an already-expired deadline is breached, and a met one has stopped its clock.
  const dueSoon = (sla ?? []).filter((row) => (
    !row.is_breached && !row.completed_at && row.hours_left !== null
    && row.hours_left >= 0 && row.hours_left <= 8
  ));
  const met = (sla ?? []).filter((row) => row.completed_at && !row.is_breached);
  const slaHealth = sla?.length ? Math.round((met.length / sla.length) * 100) : null;

  const appointmentsByWorkOrder = useMemo(() => {
    const map = new Map();
    for (const appointment of appointments) {
      if (!map.has(appointment.work_order)) map.set(appointment.work_order, []);
      map.get(appointment.work_order).push(appointment);
    }
    return map;
  }, [appointments]);

  const visibleArticles = articles.filter((article) => {
    if (!search) return true;
    const haystack = `${article.title} ${article.summary ?? ''} ${article.category?.name ?? ''}`.toLowerCase();
    return haystack.includes(search.toLowerCase());
  });

  async function advance(workOrder, toState) {
    setBusyId(workOrder.id);
    setError('');
    try {
      await transition('work_order', workOrder.id, toState);
    } catch (transitionError) {
      setError(transitionError.message);
    } finally {
      setBusyId(null);
      load();
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="service" session={session} />
      <div style={{ maxWidth: 1500, margin: '0 auto', padding: '24px 20px 60px' }}>
        <h1 style={{ fontSize: 24, margin: '0 0 4px' }}>Service console</h1>
        <p style={{ color: MUTED, margin: '0 0 24px', fontSize: 14 }}>
          What is about to breach, who is on site today, and the answers already written down.
        </p>

        {error && (
          <div style={{
            background: '#feded8', border: '1px solid #f5b2ac', color: '#ba0517',
            borderRadius: 6, padding: '9px 12px', fontSize: 14, marginBottom: 14,
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 16, marginBottom: 20 }}>
          <Metric label="Breached" value={breached.length} hint="Commitments already missed" color={LOST} />
          <Metric label="Due within 8h" value={dueSoon.length} hint="Still on time, but not for long" color={ACCENT} />
          <Metric label="Open jobs" value={(workOrders ?? []).length} hint="Work orders not completed" />
          <Metric label="SLA met" value={slaHealth === null ? '—' : `${slaHealth}%`} hint="Of the commitments on open cases">
            {slaHealth !== null && <div style={{ marginTop: 8 }}><ProgressBar percent={slaHealth} color={slaHealth >= 90 ? WON : ACCENT} /></div>}
          </Metric>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(320px, 1fr)', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'grid', gap: 20 }}>
            <Card>
              <SectionTitle right={<a href="#/admin/sla_report" style={{ fontSize: 13, color: ACCENT, textDecoration: 'none' }}>Full SLA report →</a>}>
                SLA queue
              </SectionTitle>
              {sla === null && <p style={{ color: MUTED, fontSize: 14 }}>Loading…</p>}
              {sla?.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No open case has a commitment running.</p>}
              {(sla ?? []).map((row, index) => (
                <a
                  key={`${row.concept_id}-${index}`}
                  href={`#/admin/support_case/${row.concept_id}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: INK,
                    padding: '8px 0', borderTop: `1px solid ${BORDER}`, fontSize: 14,
                  }}
                >
                  <span style={{
                    background: row.is_breached ? `${LOST}1f` : '#eef1f5',
                    color: row.is_breached ? LOST : MUTED,
                    borderRadius: 3, padding: '2px 7px', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
                  }}>
                    {row.is_breached ? 'Breached' : row.completed_at ? 'Met' : 'Running'}
                  </span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.support_case}
                    <span style={{ color: MUTED }}> · {row.account}</span>
                  </span>
                  <span style={{ color: MUTED, fontSize: 12 }}>{row.milestone}</span>
                  <span style={{ color: PRIORITY_COLORS[row.priority] ?? MUTED, fontSize: 12, fontWeight: 700 }}>{row.priority}</span>
                  <span style={{ whiteSpace: 'nowrap', fontWeight: 700, color: row.hours_left < 0 ? LOST : INK }}>
                    {row.hours_left === null ? '—' : `${row.hours_left}h`}
                  </span>
                </a>
              ))}
            </Card>

            <Card>
              <SectionTitle>Dispatch board</SectionTitle>
              {workOrders === null && <p style={{ color: MUTED, fontSize: 14 }}>Loading…</p>}
              {workOrders?.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No open job.</p>}
              {WORK_ORDER_STATES.filter((state) => state !== 'completed').map((state) => {
                const jobs = (workOrders ?? []).filter((job) => job.state === state);
                if (!jobs.length) return null;
                return (
                  <div key={state} style={{ marginBottom: 14 }}>
                    <div style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.4, color: MUTED, marginBottom: 6 }}>
                      {STATE_LABELS[state]} ({jobs.length})
                    </div>
                    {jobs.map((job) => {
                      const jobAppointments = appointmentsByWorkOrder.get(job.id) ?? [];
                      const next = jobAppointments[0];
                      return (
                        <div key={job.id} style={{ borderTop: `1px solid ${BORDER}`, padding: '8px 0', opacity: busyId === job.id ? 0.5 : 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                            <a href={`#/admin/work_order/${job.id}`} style={{ textDecoration: 'none', color: INK, fontWeight: 600, flex: 1 }}>
                              {job.subject}
                              <span style={{ color: MUTED, fontWeight: 400 }}> · {job.account?.name}</span>
                            </a>
                            <span style={{ color: PRIORITY_COLORS[job.priority] ?? MUTED, fontSize: 12, fontWeight: 700 }}>{job.priority}</span>
                            {canDispatch && state !== 'in_progress' && (
                              <button
                                onClick={() => advance(job, state === 'new' ? 'dispatched' : 'in_progress')}
                                disabled={busyId === job.id}
                                style={{
                                  border: `1px solid ${BORDER}`, background: SURFACE, color: ACCENT, borderRadius: 4,
                                  padding: '4px 9px', fontSize: 12, fontWeight: 700, cursor: 'pointer',
                                }}
                              >
                                {state === 'new' ? 'Dispatch' : 'Start'}
                              </button>
                            )}
                          </div>
                          <div style={{ color: MUTED, fontSize: 12, marginTop: 3 }}>
                            {job.work_type?.name ?? 'No work type'} · {job.territory?.name ?? 'No territory'} ·{' '}
                            {job.scheduled_start ? formatDate(job.scheduled_start, { dateStyle: 'medium', timeStyle: 'short' }) : 'not scheduled'} ·{' '}
                            {jobAppointments.length} appointment{jobAppointments.length === 1 ? '' : 's'}
                            {next?.service_resource && ` · ${next.service_resource.name}`}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
              <p style={{ color: MUTED, fontSize: 12, marginTop: 10, marginBottom: 0 }}>
                Dispatching runs the guard declared in the model: a job with no appointment booked, or without a scheduled start, is refused.
              </p>
            </Card>
          </div>

          <Card>
            <SectionTitle right={<a href="#/admin/knowledge_article" style={{ fontSize: 13, color: ACCENT, textDecoration: 'none' }}>All articles →</a>}>
              Knowledge base
            </SectionTitle>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search the answers…"
              style={{
                border: `1px solid ${BORDER}`, borderRadius: 4, padding: '7px 9px', fontSize: 13,
                background: SURFACE, color: INK, width: '100%', marginBottom: 10, fontFamily: FONT,
              }}
            />
            {visibleArticles.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>Nothing published matches that.</p>}
            {visibleArticles.map((article) => (
              <a
                key={article.id}
                href={`#/admin/knowledge_article/${article.id}`}
                style={{ display: 'block', textDecoration: 'none', color: INK, padding: '9px 0', borderTop: `1px solid ${BORDER}` }}
              >
                <strong style={{ fontSize: 14 }}>{article.title}</strong>
                {article.summary && <div style={{ color: MUTED, fontSize: 12, marginTop: 2 }}>{article.summary}</div>}
                <div style={{ color: MUTED, fontSize: 11, marginTop: 3 }}>
                  {article.category?.name ?? 'Uncategorised'} · {article.view_count} views · {article.helpful_count} found it useful
                </div>
              </a>
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, hint, color, children }) {
  return (
    <Card>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, color: MUTED, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, margin: '4px 0 2px', color: color ?? INK }}>{value}</div>
      <div style={{ color: MUTED, fontSize: 12 }}>{hint}</div>
      {children}
    </Card>
  );
}
