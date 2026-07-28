import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { useRequireSession, getPermissions, getProfile, transition, money, formatDate } from '../../lib';
import {
  Nav, Avatar, StageBadge, STAGES, STAGE_LABELS, STAGE_COLORS, OPPORTUNITY_SELECT,
  LOSS_REASON_LABELS, repName, sum, quarterOf,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, SURFACE, WON, LOST, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/pipeline — the opportunity kanban. One column per stage of the
// opportunity workflow; dropping a card on another column performs the real
// transition through the generated `workflow-transition` backend function
// (lib/workflow.js), which re-checks who owns the stage and runs the model's
// check rules — so a drop can be rejected ("Add at least one product line
// before moving to the proposal stage") and the card snaps back.
//
// Closing is where a CRM stops being a board: the last column is split into
// Won and Lost drop zones, because the model requires an outcome to close and
// a reason to lose. Dropping on Lost asks for the reason before transitioning,
// which is exactly what the check rule would otherwise refuse.
// ---------------------------------------------------------------------------

const LOSS_REASONS = Object.keys(LOSS_REASON_LABELS);

export default function PipelinePage() {
  const session = useRequireSession();

  const [deals, setDeals] = useState(null);
  const [reps, setReps] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [me, setMe] = useState(null);
  const [canWrite, setCanWrite] = useState(false);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [dragging, setDragging] = useState(null);
  const [hover, setHover] = useState(null); // { stage, outcome }
  const [pendingLoss, setPendingLoss] = useState(null); // { deal, reason }

  // Filters
  const [text, setText] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [accountFilter, setAccountFilter] = useState('');
  const [quarterFilter, setQuarterFilter] = useState('');

  useEffect(() => {
    if (!session) return;
    getPermissions().then((permissions) => setCanWrite((permissions?.opportunity ?? []).includes('write')));
    getProfile().then((profile) => setMe(profile?.record ?? null));
    supabaseClient
      .from('sales_rep')
      .select('id, first_name, last_name')
      .eq('is_active', true)
      .order('first_name')
      .then(({ data }) => setReps(data ?? []));
    supabaseClient
      .from('account')
      .select('id, name')
      .order('name')
      .then(({ data }) => setAccounts(data ?? []));
  }, [session]);

  const loadDeals = useCallback(() => {
    supabaseClient
      .from('opportunity')
      .select(OPPORTUNITY_SELECT)
      .order('close_date')
      .then(({ data, error: loadError }) => {
        if (loadError) setError(loadError.message);
        setDeals(data ?? []);
      });
  }, []);

  useEffect(() => { loadDeals(); }, [loadDeals]);

  // The quarters actually present in the data, newest first, so the selector
  // never offers an empty period.
  const quarters = useMemo(() => {
    const map = new Map();
    for (const deal of deals ?? []) {
      if (!deal.close_date) continue;
      const quarter = quarterOf(new Date(deal.close_date));
      map.set(quarter.key, quarter);
    }
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
  }, [deals]);

  const visible = useMemo(() => (deals ?? []).filter((deal) => {
    if (ownerFilter && String(deal.owner?.id ?? '') !== ownerFilter) return false;
    if (accountFilter && String(deal.account?.id ?? '') !== accountFilter) return false;
    if (quarterFilter) {
      const quarter = quarters.find((item) => item.key === quarterFilter);
      if (quarter && (!deal.close_date || deal.close_date < quarter.from || deal.close_date > quarter.to)) return false;
    }
    if (text) {
      const haystack = `${deal.name} ${deal.account?.name ?? ''} ${deal.next_step ?? ''}`.toLowerCase();
      if (!haystack.includes(text.toLowerCase())) return false;
    }
    return true;
  }), [deals, ownerFilter, accountFilter, quarterFilter, quarters, text]);

  const columnDeals = (stage, outcome) => visible.filter((deal) => (
    deal.state === stage && (outcome === undefined || deal.outcome === outcome)
  ));

  // A drop moves the deal to another stage. Closing needs an outcome first:
  // 'won' is written straight away, 'lost' opens the reason panel because the
  // check rule refuses a loss without one.
  async function handleDrop(event, stage, outcome) {
    const droppedId = Number(event.dataTransfer?.getData('text/plain'));
    const deal = dragging ?? (deals ?? []).find((candidate) => candidate.id === droppedId);
    setHover(null);
    setDragging(null);
    if (!deal) return;
    if (!canWrite) {
      setError('Your role can read the pipeline but not move deals.');
      return;
    }
    if (deal.state === stage && (outcome === undefined || deal.outcome === outcome)) return;

    if (stage === 'closed' && outcome === 'lost' && !deal.loss_reason) {
      setPendingLoss({ deal, reason: 'price' });
      return;
    }
    await move(deal, stage, outcome === undefined ? null : { outcome });
  }

  async function move(deal, stage, fields) {
    setBusyId(deal.id);
    setError('');
    try {
      if (fields) {
        const { error: updateError } = await supabaseClient.from('opportunity').update(fields).eq('id', deal.id);
        if (updateError) throw new Error(updateError.message);
      }
      if (deal.state !== stage) {
        await transition('opportunity', deal.id, stage);
      }
    } catch (moveError) {
      setError(moveError.message);
    } finally {
      setBusyId(null);
      loadDeals();
    }
  }

  const openDeals = visible.filter((deal) => deal.state !== 'closed');

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="pipeline" session={session} />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '18px 20px 40px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
          <h1 style={{ fontSize: 22, margin: 0 }}>Pipeline</h1>
          <span style={{ color: MUTED, fontSize: 14 }}>
            {openDeals.length} open deals · {money(sum(openDeals, 'amount'))} · weighted {money(sum(openDeals, 'expected_revenue'))}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Search deals…"
            style={inputStyle}
          />
          <Select
            value={ownerFilter}
            onChange={setOwnerFilter}
            placeholder="All owners"
            options={reps.map((rep) => ({ value: rep.id, label: repName(rep) }))}
          />
          {me && (
            <button
              onClick={() => setOwnerFilter(ownerFilter === String(me.id) ? '' : String(me.id))}
              style={{
                ...inputStyle, cursor: 'pointer', minWidth: 0, fontWeight: 600,
                color: ownerFilter === String(me.id) ? ACCENT : MUTED,
              }}
            >
              My deals
            </button>
          )}
          <Select
            value={accountFilter}
            onChange={setAccountFilter}
            placeholder="All accounts"
            options={accounts.map((account) => ({ value: account.id, label: account.name }))}
          />
          <Select
            value={quarterFilter}
            onChange={setQuarterFilter}
            placeholder="All close dates"
            options={quarters.map((quarter) => ({ value: quarter.key, label: quarter.label }))}
          />
        </div>

        {error && (
          <div style={{
            background: '#ffecea', border: '1px solid #f5b2ac', color: '#ae2a19',
            borderRadius: 6, padding: '9px 12px', fontSize: 14, marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        {pendingLoss && (
          <div style={{
            background: '#fff7d6', border: '1px solid #f5cd47', borderRadius: 6,
            padding: '10px 12px', fontSize: 14, marginBottom: 12, display: 'flex',
            alignItems: 'center', gap: 10, flexWrap: 'wrap',
          }}>
            <span>Closing <strong>{pendingLoss.deal.name}</strong> as lost. Why was it lost?</span>
            <Select
              value={pendingLoss.reason}
              onChange={(reason) => setPendingLoss({ ...pendingLoss, reason })}
              options={LOSS_REASONS.map((reason) => ({ value: reason, label: LOSS_REASON_LABELS[reason] }))}
            />
            <button
              onClick={() => {
                const { deal, reason } = pendingLoss;
                setPendingLoss(null);
                move(deal, 'closed', { outcome: 'lost', loss_reason: reason });
              }}
              style={{ ...inputStyle, cursor: 'pointer', minWidth: 0, background: ACCENT, color: '#fff', border: 'none', fontWeight: 700 }}
            >
              Close as lost
            </button>
            <button onClick={() => setPendingLoss(null)} style={{ ...inputStyle, cursor: 'pointer', minWidth: 0 }}>
              Cancel
            </button>
          </div>
        )}

        {deals === null && <p style={{ color: MUTED }}>Loading…</p>}

        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${STAGES.length}, minmax(230px, 1fr))`, gap: 10, overflowX: 'auto', alignItems: 'start' }}>
          {STAGES.filter((stage) => stage !== 'closed').map((stage) => (
            <Column
              key={stage}
              title={STAGE_LABELS[stage]}
              color={STAGE_COLORS[stage]}
              deals={columnDeals(stage)}
              hovered={hover?.stage === stage && !hover?.outcome}
              onDragOver={(event) => { event.preventDefault(); setHover({ stage }); }}
              onDrop={(event) => { event.preventDefault(); handleDrop(event, stage); }}
              renderCard={(deal) => (
                <DealCard
                  key={deal.id}
                  deal={deal}
                  busy={busyId === deal.id}
                  draggable={canWrite}
                  onDragStart={(event) => {
                    event.dataTransfer.setData('text/plain', String(deal.id));
                    event.dataTransfer.effectAllowed = 'move';
                    setDragging(deal);
                  }}
                  onDragEnd={() => { setDragging(null); setHover(null); }}
                />
              )}
            />
          ))}

          {/* The closed column is split: the model needs an outcome to close a
              deal, so the board asks for it at the moment of the drop. */}
          <div style={{ display: 'grid', gap: 10 }}>
            <Column
              title="Closed won"
              color={WON}
              deals={columnDeals('closed', 'won')}
              hovered={hover?.stage === 'closed' && hover?.outcome === 'won'}
              onDragOver={(event) => { event.preventDefault(); setHover({ stage: 'closed', outcome: 'won' }); }}
              onDrop={(event) => { event.preventDefault(); handleDrop(event, 'closed', 'won'); }}
              renderCard={(deal) => <DealCard key={deal.id} deal={deal} busy={busyId === deal.id} draggable={false} />}
            />
            <Column
              title="Closed lost"
              color={LOST}
              deals={columnDeals('closed', 'lost')}
              hovered={hover?.stage === 'closed' && hover?.outcome === 'lost'}
              onDragOver={(event) => { event.preventDefault(); setHover({ stage: 'closed', outcome: 'lost' }); }}
              onDrop={(event) => { event.preventDefault(); handleDrop(event, 'closed', 'lost'); }}
              renderCard={(deal) => <DealCard key={deal.id} deal={deal} busy={busyId === deal.id} draggable={false} />}
            />
          </div>
        </div>

        {deals !== null && visible.length === 0 && (
          <p style={{ color: MUTED, fontSize: 14 }}>No deal matches the current filters.</p>
        )}

        <p style={{ color: MUTED, fontSize: 12, marginTop: 18 }}>
          Moving a card runs the same server-side checks as the backoffice: a deal needs an amount and product lines to reach
          Proposal, an owner and a next step to be negotiated, and only a sales manager may close one.
        </p>
      </div>
    </div>
  );
}

function Column({ title, color, deals, hovered, renderCard, onDragOver, onDrop }) {
  return (
    <div
      onDragOver={onDragOver}
      onDrop={onDrop}
      style={{
        background: hovered ? '#e3f1fd' : '#e9edf2', borderRadius: 6, minHeight: 130, paddingBottom: 8,
      }}
    >
      <div style={{ padding: '10px 12px 8px' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 800,
          textTransform: 'uppercase', letterSpacing: 0.5, color,
        }}>
          <span>{title}</span>
          <span style={{ color: MUTED, fontWeight: 600 }}>{deals.length}</span>
        </div>
        <div style={{ fontSize: 12, color: MUTED, marginTop: 2 }}>
          {money(sum(deals, 'amount'))}
          <span style={{ opacity: 0.8 }}> · w. {money(sum(deals, 'expected_revenue'))}</span>
        </div>
      </div>
      {deals.map(renderCard)}
    </div>
  );
}

function DealCard({ deal, busy, draggable, ...handlers }) {
  const overdue = deal.state !== 'closed' && deal.close_date && deal.close_date < new Date().toISOString().slice(0, 10);
  return (
    <div
      draggable={draggable && !busy}
      {...handlers}
      style={{
        background: SURFACE, borderRadius: 4, margin: '0 8px 8px', padding: '10px 10px 8px',
        boxShadow: '0 1px 1px rgba(9,30,66,0.25)', cursor: draggable ? 'grab' : 'default',
        opacity: busy ? 0.5 : 1,
      }}
    >
      <a
        href={`#/admin/opportunity/${deal.id}`}
        onClick={(event) => event.stopPropagation()}
        style={{ textDecoration: 'none', color: INK, fontSize: 14, fontWeight: 600, display: 'block' }}
      >
        {deal.name}
      </a>
      <div style={{ color: MUTED, fontSize: 12, margin: '2px 0 8px' }}>{deal.account?.name}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <strong style={{ fontSize: 14 }}>{money(deal.amount)}</strong>
        <span style={{ background: '#eef1f5', color: MUTED, borderRadius: 10, padding: '1px 7px', fontSize: 11, fontWeight: 700 }}>
          {deal.probability}%
        </span>
        <span style={{ flex: 1 }} />
        <Avatar rep={deal.owner} size={22} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: overdue ? LOST : MUTED }}>
        <span>{formatDate(deal.close_date)}</span>
        {deal.state === 'closed' && <StageBadge stage="closed" outcome={deal.outcome} />}
        {deal.state === 'closed' && deal.loss_reason && <span>· {LOSS_REASON_LABELS[deal.loss_reason]}</span>}
      </div>
      {deal.next_step && deal.state !== 'closed' && (
        <div style={{ fontSize: 12, color: MUTED, marginTop: 6, borderTop: `1px solid ${BORDER}`, paddingTop: 6 }}>
          → {deal.next_step}
        </div>
      )}
    </div>
  );
}

export const inputStyle = {
  border: `1px solid ${BORDER}`, borderRadius: 4, padding: '6px 9px', fontSize: 13,
  background: SURFACE, color: INK, minWidth: 150,
};

export function Select({ value, onChange, options, placeholder }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}
