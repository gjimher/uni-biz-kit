import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { supabaseClient } from '../../supabaseClient';
import {
  useRequireSession, getProfile, getPermissions, signOut, money, formatDate,
  createPaymentIntent, confirmPayment, paymentsDevMode,
} from '../lib';

// ---------------------------------------------------------------------------
// Sales console — the page a rep lands on. The whole portal is private: this
// page redirects to /signin when there is no session. It shows the deals, the
// activities, the leads and the cases that belong to the signed-in user, and
// links the two working pages (pipeline, forecast) plus the generated
// backoffice.
//
// This file also owns the shared look of the portal (palette, stage colours,
// badges) and the top navigation, which the /priv pages import from here —
// same convention as agile-app and intranet-app.
// ---------------------------------------------------------------------------

export const ACCENT = '#0176d3';
export const ACCENT_SOFT = '#eaf5fe';
export const INK = '#181818';
export const MUTED = '#5c6b7a';
export const BORDER = '#d8dde6';
export const BG_SOFT = '#f3f6f9';
export const SURFACE = '#ffffff';
export const WON = '#2e844a';
export const LOST = '#ba0517';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// Stages of the opportunity workflow, in order — the columns of the pipeline.
export const STAGES = ['prospecting', 'qualification', 'needs_analysis', 'proposal', 'negotiation', 'closed'];
export const STAGE_LABELS = {
  prospecting: 'Prospecting', qualification: 'Qualification', needs_analysis: 'Needs analysis',
  proposal: 'Proposal', negotiation: 'Negotiation', closed: 'Closed',
};
export const STAGE_COLORS = {
  prospecting: '#8b9bab', qualification: '#5c6b7a', needs_analysis: '#0176d3',
  proposal: '#7f56d9', negotiation: '#dd7a01', closed: '#2e844a',
};

// Forecast buckets, as the calculated forecast_category produces them.
export const FORECAST_CATEGORIES = ['pipeline', 'best_case', 'commit', 'closed', 'omitted'];
export const FORECAST_LABELS = {
  pipeline: 'Pipeline', best_case: 'Best case', commit: 'Commit', closed: 'Closed', omitted: 'Omitted',
};

export const LOSS_REASON_LABELS = {
  price: 'Price', product_fit: 'Product fit', competitor: 'Competitor',
  no_decision: 'No decision', timing: 'Timing', lost_contact: 'Lost contact', other: 'Other',
};

// Every page renders a deal from these columns.
export const OPPORTUNITY_SELECT =
  'id, name, state, outcome, loss_reason, type, amount, expected_revenue, probability, '
  + 'forecast_category, close_date, next_step, lead_source, '
  + 'account(id, name), owner(id, first_name, last_name), primary_contact(id, first_name, last_name)';

export const repName = (rep) => (rep ? `${rep.first_name} ${rep.last_name}` : 'Unassigned');
export const initials = (rep) => (rep ? `${rep.first_name[0] ?? ''}${rep.last_name[0] ?? ''}`.toUpperCase() : '–');
export const sum = (rows, field) => rows.reduce((total, row) => total + Number(row[field] ?? 0), 0);

// Quarter of a date as { label, from, to } — the unit a forecast is read in.
export function quarterOf(date) {
  const quarter = Math.floor(date.getMonth() / 3);
  const from = new Date(Date.UTC(date.getFullYear(), quarter * 3, 1));
  const to = new Date(Date.UTC(date.getFullYear(), quarter * 3 + 3, 0));
  return {
    key: `${date.getFullYear()}-Q${quarter + 1}`,
    label: `Q${quarter + 1} ${date.getFullYear()}`,
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

export function StageBadge({ stage, outcome }) {
  const closed = stage === 'closed';
  const color = closed ? (outcome === 'won' ? WON : LOST) : (STAGE_COLORS[stage] ?? MUTED);
  const label = closed ? (outcome === 'won' ? 'Closed won' : outcome === 'lost' ? 'Closed lost' : 'Closed') : (STAGE_LABELS[stage] ?? stage);
  return (
    <span style={{
      background: `${color}1f`, color, borderRadius: 3, padding: '2px 7px', fontSize: 11,
      fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.3, whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

export function Avatar({ rep, size = 24 }) {
  return (
    <span
      title={repName(rep)}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: size, height: size, borderRadius: '50%', flexShrink: 0,
        background: rep ? ACCENT_SOFT : '#e5e9ef', color: rep ? ACCENT : MUTED,
        fontSize: size * 0.42, fontWeight: 700, border: `1px solid ${BORDER}`,
      }}
    >
      {initials(rep)}
    </span>
  );
}

export function Card({ children, style }) {
  return (
    <div style={{
      background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8,
      padding: '16px 18px', ...style,
    }}>
      {children}
    </div>
  );
}

export function SectionTitle({ children, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, margin: '0 0 10px' }}>
      <h2 style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, color: MUTED, margin: 0, fontWeight: 700 }}>
        {children}
      </h2>
      {right}
    </div>
  );
}

export function ProgressBar({ percent, color = ACCENT }) {
  return (
    <div style={{ background: '#e5e9ef', borderRadius: 3, height: 8, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, Math.max(0, percent))}%`, background: color, height: '100%' }} />
    </div>
  );
}

// Top navigation shared by every portal page.
export function Nav({ current, session }) {
  const links = [
    { href: '#/', label: 'Console', key: 'home' },
    { href: '#/priv/pipeline', label: 'Pipeline', key: 'pipeline' },
    { href: '#/priv/forecast', label: 'Forecast', key: 'forecast' },
    { href: '#/priv/service', label: 'Service', key: 'service' },
  ];
  return (
    <header style={{ background: SURFACE, borderBottom: `1px solid ${BORDER}`, position: 'sticky', top: 0, zIndex: 30 }}>
      <div style={{ maxWidth: 1500, margin: '0 auto', padding: '0 20px', display: 'flex', alignItems: 'center', gap: 20, height: 52 }}>
        <a href="#/" style={{ textDecoration: 'none', color: INK, fontWeight: 800, fontSize: 17, letterSpacing: -0.3 }}>
          <span style={{ color: ACCENT }}>☁</span> UBK CRM
        </a>
        <nav style={{ display: 'flex', gap: 4, flex: 1 }}>
          {links.map((link) => (
            <a
              key={link.key}
              href={link.href}
              style={{
                textDecoration: 'none', fontSize: 14, fontWeight: 600, padding: '6px 10px',
                borderRadius: 4, color: current === link.key ? ACCENT : MUTED,
                background: current === link.key ? ACCENT_SOFT : 'transparent',
              }}
            >
              {link.label}
            </a>
          ))}
        </nav>
        <a href="#/admin" style={{ textDecoration: 'none', fontSize: 13, fontWeight: 600, color: MUTED }}>
          Backoffice
        </a>
        <span style={{ fontSize: 13, color: MUTED, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {session?.user?.email}
        </span>
        <button
          onClick={() => signOut().then(() => { window.location.hash = '#/signin'; })}
          style={{
            border: `1px solid ${BORDER}`, background: SURFACE, color: INK, borderRadius: 4,
            padding: '5px 10px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

const today = () => new Date().toISOString().slice(0, 10);
const yearStart = () => `${new Date().getFullYear()}-01-01`;

export default function SalesConsole() {
  const session = useRequireSession(); // redirects to /signin when signed out
  const [me, setMe] = useState(undefined); // undefined = loading, null = no profile row
  const [openDeals, setOpenDeals] = useState(null);
  const [wonDeals, setWonDeals] = useState([]);
  const [activities, setActivities] = useState(null);
  const [leads, setLeads] = useState([]);
  const [cases, setCases] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [canBill, setCanBill] = useState(false);
  const [payingInvoice, setPayingInvoice] = useState(null);

  const loadInvoices = useCallback(() => {
    supabaseClient
      .from('invoice')
      .select('id, id_presentation, reference, state, issue_date, due_date, total, paid_amount, balance, account(id, name)')
      .gt('balance', 0)
      .order('due_date')
      .then(({ data }) => setInvoices(data ?? []));
  }, []);

  useEffect(() => {
    if (!session) return;
    getProfile().then((profile) => setMe(profile?.record ?? null));
    getPermissions().then((permissions) => setCanBill(
      (permissions?.invoice ?? []).includes('write') || (permissions?.['*'] ?? []).includes('write'),
    ));
    loadInvoices();
  }, [session, loadInvoices]);

  useEffect(() => {
    if (!me) {
      if (me === null) { setOpenDeals([]); setActivities([]); }
      return;
    }
    supabaseClient
      .from('opportunity')
      .select(OPPORTUNITY_SELECT)
      .eq('owner', me.id)
      .neq('state', 'closed')
      .order('close_date')
      .then(({ data }) => setOpenDeals(data ?? []));
    // Won this year: what the quota attainment is measured on.
    supabaseClient
      .from('opportunity')
      .select('id, name, amount, close_date, account(id, name)')
      .eq('owner', me.id)
      .eq('state', 'closed')
      .eq('outcome', 'won')
      .gte('close_date', yearStart())
      .then(({ data }) => setWonDeals(data ?? []));
    supabaseClient
      .from('activity')
      .select('id, subject, type, status, priority, due_date, account(id, name), contact(id, first_name, last_name), lead(id, company), opportunity(id, name), support_case(id, subject)')
      .eq('owner', me.id)
      .neq('status', 'completed')
      .order('due_date')
      .then(({ data }) => setActivities(data ?? []));
    supabaseClient
      .from('lead')
      .select('id, id_presentation, company, first_name, last_name, status, rating, email')
      .eq('owner', me.id)
      .not('status', 'in', '("converted","unqualified")')
      .order('id', { ascending: false })
      .then(({ data }) => setLeads(data ?? []));
    supabaseClient
      .from('support_case')
      .select('id, id_presentation, subject, state, priority, account(id, name)')
      .eq('owner', me.id)
      .neq('state', 'closed')
      .order('id', { ascending: false })
      .then(({ data }) => setCases(data ?? []));
  }, [me]);

  const pipeline = useMemo(() => sum(openDeals ?? [], 'amount'), [openDeals]);
  const weighted = useMemo(() => sum(openDeals ?? [], 'expected_revenue'), [openDeals]);
  const won = useMemo(() => sum(wonDeals, 'amount'), [wonDeals]);
  const quota = Number(me?.quota_annual ?? 0);
  const attainment = quota ? Math.round((won / quota) * 100) : null;

  const overdue = (activities ?? []).filter((a) => a.due_date && a.due_date < today());
  const dueToday = (activities ?? []).filter((a) => a.due_date === today());
  const upcoming = (activities ?? []).filter((a) => !a.due_date || a.due_date > today());

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="home" session={session} />
      <div style={{ maxWidth: 1500, margin: '0 auto', padding: '24px 20px 60px' }}>
        <h1 style={{ fontSize: 24, margin: '0 0 4px' }}>
          {me ? `Hello, ${me.first_name}` : 'Sales console'}
        </h1>
        <p style={{ color: MUTED, margin: '0 0 24px', fontSize: 14 }}>
          {me === null
            ? 'This account has no team profile, so nothing is assigned to it. You can still open the pipeline and the forecast.'
            : 'Your deals, your activities and your queues.'}
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 20 }}>
          <Metric label="Open pipeline" value={money(pipeline)} hint={`${(openDeals ?? []).length} open deals`} />
          <Metric label="Weighted pipeline" value={money(weighted)} hint="Amount × stage probability" />
          <Metric label="Closed won this year" value={money(won)} hint={`${wonDeals.length} deals`} />
          <Metric
            label="Quota attainment"
            value={attainment === null ? '—' : `${attainment}%`}
            hint={quota ? `${money(won)} of ${money(quota)}` : 'No quota set'}
          >
            {attainment !== null && <div style={{ marginTop: 8 }}><ProgressBar percent={attainment} color={attainment >= 100 ? WON : ACCENT} /></div>}
          </Metric>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(300px, 1fr)', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'grid', gap: 20 }}>
            <Card>
              <SectionTitle right={<a href="#/priv/pipeline" style={{ fontSize: 13, color: ACCENT, textDecoration: 'none' }}>Open the pipeline →</a>}>
                My open deals
              </SectionTitle>
              {openDeals === null && <p style={{ color: MUTED, fontSize: 14 }}>Loading…</p>}
              {openDeals?.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No open deals. Convert a qualified lead to start one.</p>}
              {STAGES.filter((stage) => stage !== 'closed').map((stage) => {
                const deals = (openDeals ?? []).filter((deal) => deal.state === stage);
                if (!deals.length) return null;
                return (
                  <div key={stage} style={{ marginBottom: 14 }}>
                    <div style={{ marginBottom: 6 }}><StageBadge stage={stage} /></div>
                    {deals.map((deal) => <DealRow key={deal.id} deal={deal} />)}
                  </div>
                );
              })}
            </Card>

            <Card>
              <SectionTitle>My activities</SectionTitle>
              {activities === null && <p style={{ color: MUTED, fontSize: 14 }}>Loading…</p>}
              {activities?.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>Nothing pending. Log the next step of a deal from the backoffice.</p>}
              <ActivityGroup title="Overdue" activities={overdue} color={LOST} />
              <ActivityGroup title="Due today" activities={dueToday} color={ACCENT} />
              <ActivityGroup title="Coming up" activities={upcoming} color={MUTED} />
            </Card>
          </div>

          <div style={{ display: 'grid', gap: 20 }}>
            <Card>
              <SectionTitle right={<a href="#/admin/lead" style={{ fontSize: 13, color: ACCENT, textDecoration: 'none' }}>All leads →</a>}>
                My leads
              </SectionTitle>
              {leads.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No open leads.</p>}
              {leads.map((lead) => (
                <a
                  key={lead.id}
                  href={`#/admin/lead/${lead.id}`}
                  style={{ display: 'block', textDecoration: 'none', color: INK, padding: '9px 0', borderTop: `1px solid ${BORDER}` }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <strong style={{ fontSize: 14, flex: 1 }}>{lead.company}</strong>
                    <span style={{
                      background: lead.status === 'qualified' ? `${WON}1f` : '#eef1f5',
                      color: lead.status === 'qualified' ? WON : MUTED,
                      borderRadius: 3, padding: '1px 6px', fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                    }}>{lead.status}</span>
                  </div>
                  <div style={{ color: MUTED, fontSize: 12, marginTop: 2 }}>
                    {lead.first_name} {lead.last_name}{lead.rating ? ` · ${lead.rating}` : ''}
                  </div>
                </a>
              ))}
              <p style={{ color: MUTED, fontSize: 12, marginTop: 10, marginBottom: 0 }}>
                A qualified lead is converted from its record in the backoffice: the <strong>Convert Lead</strong> action creates the
                account, the contact and the deal in one go.
              </p>
            </Card>

            {canBill && <Card>
              <SectionTitle right={<a href="#/admin/invoice" style={{ fontSize: 13, color: ACCENT, textDecoration: 'none' }}>All invoices →</a>}>
                Outstanding invoices
              </SectionTitle>
              {invoices.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>Everything is paid.</p>}
              {invoices.map((invoice) => {
                const overdue = invoice.due_date && invoice.due_date < today();
                return (
                  <div key={invoice.id} style={{ padding: '9px 0', borderTop: `1px solid ${BORDER}` }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <a href={`#/admin/invoice/${invoice.id}`} style={{ textDecoration: 'none', color: INK, fontWeight: 600, flex: 1 }}>
                        {invoice.reference}
                        <span style={{ color: MUTED, fontWeight: 400 }}> · {invoice.account?.name}</span>
                      </a>
                      <strong>{money(invoice.balance)}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3 }}>
                      <span style={{ color: overdue ? LOST : MUTED, fontSize: 12, flex: 1 }}>
                        {invoice.state} · due {formatDate(invoice.due_date)}{overdue ? ' · overdue' : ''}
                        {Number(invoice.paid_amount) > 0 && ` · ${money(invoice.paid_amount)} already paid`}
                      </span>
                      <button
                        onClick={() => setPayingInvoice(invoice)}
                        style={{
                          border: `1px solid ${BORDER}`, background: SURFACE, color: ACCENT, borderRadius: 4,
                          padding: '3px 8px', fontSize: 12, fontWeight: 700, cursor: 'pointer',
                        }}
                      >
                        Pay by card
                      </button>
                    </div>
                  </div>
                );
              })}
            </Card>}

            <Card>
              <SectionTitle>My open cases</SectionTitle>
              {cases.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No case assigned to you.</p>}
              {cases.map((supportCase) => (
                <a
                  key={supportCase.id}
                  href={`#/admin/support_case/${supportCase.id}`}
                  style={{ display: 'block', textDecoration: 'none', color: INK, padding: '9px 0', borderTop: `1px solid ${BORDER}` }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 700, color: ACCENT }}>#{supportCase.id}</span>
                    <span style={{ flex: 1, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {supportCase.subject}
                    </span>
                  </div>
                  <div style={{ color: MUTED, fontSize: 12, marginTop: 2 }}>
                    {supportCase.account?.name} · {supportCase.state} · {supportCase.priority}
                  </div>
                </a>
              ))}
            </Card>
          </div>
        </div>
      </div>

      {payingInvoice && (
        <PayInvoiceDialog
          invoice={payingInvoice}
          onClose={() => setPayingInvoice(null)}
          onPaid={() => { setPayingInvoice(null); loadInvoices(); }}
        />
      )}
    </div>
  );
}

// Charges the invoice through the generated `payment` backend function, which reads the
// amount from the record itself (system.jsonc points it at invoice.balance) — the browser
// never says how much to charge.
function PayInvoiceDialog({ invoice, onClose, onPaid }) {
  const [card, setCard] = useState({ number: '', exp_month: '', exp_year: '', cvc: '' });
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const pay = async () => {
    setBusy(true);
    setError('');
    try {
      setStatus('Creating the payment…');
      await createPaymentIntent(invoice.id);
      setStatus('Confirming with the provider…');
      const result = await confirmPayment(invoice.id, {
        number: card.number.replace(/\s+/g, ''),
        exp_month: Number(card.exp_month),
        exp_year: Number(card.exp_year),
        cvc: card.cvc,
      });
      if (result?.status && result.status !== 'paid') throw new Error(`Payment ${result.status}`);
      onPaid();
    } catch (payError) {
      setError(payError.message);
      setStatus('');
      setBusy(false);
    }
  };

  const field = (label, key, placeholder) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: MUTED }}>
      {label}
      <input
        value={card[key]}
        onChange={(event) => setCard({ ...card, [key]: event.target.value })}
        placeholder={placeholder}
        style={{ border: `1px solid ${BORDER}`, borderRadius: 4, padding: '8px 9px', fontSize: 14, color: INK, fontFamily: FONT }}
      />
    </label>
  );

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(24,24,24,0.45)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 16,
      }}
    >
      <div onClick={(event) => event.stopPropagation()} style={{ background: SURFACE, borderRadius: 10, padding: 22, width: 'min(420px, 100%)' }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 18 }}>Pay {invoice.reference}</h2>
        <p style={{ color: MUTED, fontSize: 13, margin: '0 0 16px' }}>
          {invoice.account?.name} · outstanding <strong style={{ color: INK }}>{money(invoice.balance)}</strong>
        </p>
        <div style={{ display: 'grid', gap: 10 }}>
          {field('Card number', 'number', '4242 4242 4242 4242')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            {field('Month', 'exp_month', '12')}
            {field('Year', 'exp_year', '2030')}
            {field('CVC', 'cvc', '123')}
          </div>
        </div>
        {paymentsDevMode && (
          <p style={{ color: MUTED, fontSize: 12, marginTop: 10 }}>
            Development simulator: any card is accepted except <code>4000 0000 0000 0002</code>, which is declined.
          </p>
        )}
        {status && <p style={{ color: MUTED, fontSize: 13, marginTop: 10 }}>{status}</p>}
        {error && (
          <p style={{ color: LOST, background: '#feded8', borderRadius: 6, padding: '8px 10px', fontSize: 13, marginTop: 10 }}>
            {error}
          </p>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button
            onClick={onClose}
            disabled={busy}
            style={{ border: `1px solid ${BORDER}`, background: SURFACE, color: INK, borderRadius: 4, padding: '8px 12px', fontSize: 13, cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={pay}
            disabled={busy || !card.number}
            style={{
              border: 'none', background: busy || !card.number ? '#c9c9c9' : ACCENT, color: '#fff', borderRadius: 4,
              padding: '8px 14px', fontSize: 13, fontWeight: 700, cursor: busy ? 'default' : 'pointer',
            }}
          >
            Pay {money(invoice.balance)}
          </button>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, hint, children }) {
  return (
    <Card>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, color: MUTED, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, margin: '4px 0 2px' }}>{value}</div>
      <div style={{ color: MUTED, fontSize: 12 }}>{hint}</div>
      {children}
    </Card>
  );
}

function DealRow({ deal }) {
  return (
    <a
      href={`#/admin/opportunity/${deal.id}`}
      style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: INK, padding: '6px 0', fontSize: 14 }}
    >
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {deal.name}
        <span style={{ color: MUTED }}> · {deal.account?.name}</span>
      </span>
      <span style={{ color: MUTED, fontSize: 12, whiteSpace: 'nowrap' }}>{formatDate(deal.close_date)}</span>
      <strong style={{ whiteSpace: 'nowrap' }}>{money(deal.amount)}</strong>
      <span style={{ background: '#eef1f5', color: MUTED, borderRadius: 10, padding: '1px 8px', fontSize: 11, fontWeight: 700 }}>
        {deal.probability}%
      </span>
    </a>
  );
}

const ACTIVITY_MARK = { call: '📞', email: '✉', meeting: '👥', demo: '▶', task: '✓' };

function ActivityGroup({ title, activities, color }) {
  if (!activities.length) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.4, color, marginBottom: 4 }}>
        {title} ({activities.length})
      </div>
      {activities.map((activity) => {
        const target = activity.opportunity?.name ?? activity.support_case?.subject ?? activity.lead?.company ?? activity.account?.name;
        return (
          <a
            key={activity.id}
            href={`#/admin/activity/${activity.id}`}
            style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', color: INK, padding: '5px 0', fontSize: 14 }}
          >
            <span title={activity.type}>{ACTIVITY_MARK[activity.type] ?? '✓'}</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activity.subject}
              {target && <span style={{ color: MUTED }}> · {target}</span>}
            </span>
            <span style={{ color: MUTED, fontSize: 12, whiteSpace: 'nowrap' }}>{formatDate(activity.due_date)}</span>
          </a>
        );
      })}
    </div>
  );
}
