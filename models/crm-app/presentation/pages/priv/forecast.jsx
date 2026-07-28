import React, { useEffect, useMemo, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { useRequireSession, money, number } from '../../lib';
import {
  Nav, Card, SectionTitle, ProgressBar, StageBadge, Avatar,
  FORECAST_CATEGORIES, FORECAST_LABELS, LOSS_REASON_LABELS, STAGE_LABELS,
  repName, sum, quarterOf,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, SURFACE, WON, LOST, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/forecast — the numbers a sales manager reviews every week, all read
// from the model's calculated fields: forecast_category and expected_revenue
// come from the stage of each deal (see concepts.jsonc), so the forecast is a
// consequence of moving cards on the pipeline, never a separate spreadsheet.
//
// Everything is scoped to a quarter by close date, which is the period a
// commitment is made in. Quota attainment compares the quarter's won amount
// with a quarter of the rep's annual quota.
// ---------------------------------------------------------------------------

const CATEGORY_COLORS = {
  pipeline: '#8b9bab', best_case: '#7f56d9', commit: '#dd7a01', closed: WON, omitted: '#b0b8c1',
};

export default function ForecastPage() {
  const session = useRequireSession();
  const [deals, setDeals] = useState(null);
  const [reps, setReps] = useState([]);
  const [quotas, setQuotas] = useState([]);
  const [quarterKey, setQuarterKey] = useState(quarterOf(new Date()).key);

  useEffect(() => {
    if (!session) return;
    supabaseClient
      .from('opportunity')
      .select('id, name, state, outcome, loss_reason, type, lead_source, amount, expected_revenue, probability, forecast_category, close_date, account(id, name), owner(id, first_name, last_name)')
      .order('close_date')
      .then(({ data }) => setDeals(data ?? []));
    supabaseClient
      .from('sales_rep')
      .select('id, first_name, last_name, quota_annual, is_active, department')
      .eq('is_active', true)
      .order('first_name')
      .then(({ data }) => setReps(data ?? []));
    supabaseClient
      .from('quota_period')
      .select('id, label, amount, period_start, period_end, sales_rep')
      .then(({ data }) => setQuotas(data ?? []));
  }, [session]);

  const quarters = useMemo(() => {
    const map = new Map();
    for (const deal of deals ?? []) {
      if (!deal.close_date) continue;
      const quarter = quarterOf(new Date(deal.close_date));
      map.set(quarter.key, quarter);
    }
    const current = quarterOf(new Date());
    map.set(current.key, current);
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
  }, [deals]);

  const quarter = quarters.find((item) => item.key === quarterKey) ?? quarterOf(new Date());

  const inQuarter = useMemo(() => (deals ?? []).filter((deal) => (
    deal.close_date && deal.close_date >= quarter.from && deal.close_date <= quarter.to
  )), [deals, quarter]);

  const open = inQuarter.filter((deal) => deal.state !== 'closed');
  const closed = inQuarter.filter((deal) => deal.state === 'closed');
  const won = closed.filter((deal) => deal.outcome === 'won');
  const lost = closed.filter((deal) => deal.outcome === 'lost');
  const winRate = won.length + lost.length ? Math.round((won.length / (won.length + lost.length)) * 100) : null;

  const byCategory = FORECAST_CATEGORIES.map((category) => {
    const rows = inQuarter.filter((deal) => deal.forecast_category === category);
    return { category, rows, amount: sum(rows, 'amount'), weighted: sum(rows, 'expected_revenue') };
  });

  const commitAndClosed = sum(
    inQuarter.filter((deal) => ['commit', 'closed'].includes(deal.forecast_category)),
    'amount',
  );

  // The quota of the period if the rep has one, otherwise a quarter of the annual figure.
  const targetFor = (rep) => {
    const period = quotas.find((row) => row.sales_rep === rep.id && row.label === quarter.key);
    return period ? Number(period.amount) : Number(rep.quota_annual ?? 0) / 4;
  };
  const quotaTotal = reps.reduce((total, rep) => total + targetFor(rep), 0);
  const attainment = quotaTotal ? Math.round((sum(won, 'amount') / quotaTotal) * 100) : null;

  const byRep = reps
    .filter((rep) => targetFor(rep) > 0 || inQuarter.some((deal) => deal.owner?.id === rep.id))
    .map((rep) => {
      const repOpen = open.filter((deal) => deal.owner?.id === rep.id);
      const repWon = won.filter((deal) => deal.owner?.id === rep.id);
      const target = targetFor(rep);
      return {
        rep,
        target,
        open: sum(repOpen, 'amount'),
        weighted: sum(repOpen, 'expected_revenue'),
        won: sum(repWon, 'amount'),
        percent: target ? Math.round((sum(repWon, 'amount') / target) * 100) : null,
        deals: repOpen.length,
      };
    })
    .sort((a, b) => b.won - a.won);

  const byLossReason = Object.keys(LOSS_REASON_LABELS)
    .map((reason) => ({ reason, rows: lost.filter((deal) => deal.loss_reason === reason) }))
    .filter((row) => row.rows.length)
    .sort((a, b) => b.rows.length - a.rows.length);

  const bySource = useMemo(() => {
    const map = new Map();
    for (const deal of open) {
      const key = deal.lead_source ?? 'unknown';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(deal);
    }
    return [...map.entries()]
      .map(([source, rows]) => ({ source, rows, amount: sum(rows, 'amount') }))
      .sort((a, b) => b.amount - a.amount);
  }, [open]);

  const maxCategoryAmount = Math.max(1, ...byCategory.map((row) => row.amount));

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="forecast" session={session} />
      <div style={{ maxWidth: 1500, margin: '0 auto', padding: '18px 20px 60px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <h1 style={{ fontSize: 22, margin: 0 }}>Forecast</h1>
          <select
            value={quarter.key}
            onChange={(event) => setQuarterKey(event.target.value)}
            style={{
              border: `1px solid ${BORDER}`, borderRadius: 4, padding: '6px 9px', fontSize: 13,
              background: SURFACE, color: INK, cursor: 'pointer',
            }}
          >
            {quarters.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
          </select>
          <span style={{ color: MUTED, fontSize: 14 }}>
            deals closing between {quarter.from} and {quarter.to}
          </span>
        </div>

        {deals === null && <p style={{ color: MUTED }}>Loading…</p>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 16, marginBottom: 20 }}>
          <Metric label="Open pipeline" value={money(sum(open, 'amount'))} hint={`${open.length} deals in the quarter`} />
          <Metric label="Weighted" value={money(sum(open, 'expected_revenue'))} hint="Amount × stage probability" />
          <Metric label="Commit + closed" value={money(commitAndClosed)} hint="What the team is standing behind" />
          <Metric label="Closed won" value={money(sum(won, 'amount'))} hint={`${won.length} deals · win rate ${winRate === null ? '—' : `${winRate}%`}`} />
          <Metric
            label="Team quota attainment"
            value={attainment === null ? '—' : `${attainment}%`}
            hint={quotaTotal ? `${money(sum(won, 'amount'))} of ${money(quotaTotal)}` : 'No quotas set'}
          >
            {attainment !== null && <div style={{ marginTop: 8 }}><ProgressBar percent={attainment} color={attainment >= 100 ? WON : ACCENT} /></div>}
          </Metric>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(320px, 0.8fr)', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'grid', gap: 20 }}>
            <Card>
              <SectionTitle>By forecast category</SectionTitle>
              <p style={{ color: MUTED, fontSize: 12, margin: '-4px 0 12px' }}>
                The category is derived from the stage of each deal, so it moves when the deal moves.
              </p>
              {byCategory.map(({ category, rows, amount, weighted }) => (
                <div key={category} style={{ padding: '8px 0', borderTop: `1px solid ${BORDER}` }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                    <strong style={{ fontSize: 14, color: CATEGORY_COLORS[category] }}>{FORECAST_LABELS[category]}</strong>
                    <span style={{ color: MUTED, fontSize: 12 }}>{rows.length} deals</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ color: MUTED, fontSize: 12 }}>weighted {money(weighted)}</span>
                    <strong style={{ fontSize: 14 }}>{money(amount)}</strong>
                  </div>
                  <ProgressBar percent={(amount / maxCategoryAmount) * 100} color={CATEGORY_COLORS[category]} />
                </div>
              ))}
            </Card>

            <Card>
              <SectionTitle>By sales rep</SectionTitle>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ color: MUTED, fontSize: 12, textAlign: 'right' }}>
                      <th style={{ textAlign: 'left', padding: '6px 6px 6px 0', fontWeight: 600 }}>Rep</th>
                      <th style={{ padding: 6, fontWeight: 600 }}>Open</th>
                      <th style={{ padding: 6, fontWeight: 600 }}>Weighted</th>
                      <th style={{ padding: 6, fontWeight: 600 }}>Won</th>
                      <th style={{ padding: 6, fontWeight: 600 }}>Quarter target</th>
                      <th style={{ padding: 6, fontWeight: 600, minWidth: 130 }}>Attainment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byRep.map((row) => (
                      <tr key={row.rep.id} style={{ borderTop: `1px solid ${BORDER}`, textAlign: 'right' }}>
                        <td style={{ textAlign: 'left', padding: '8px 6px 8px 0' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                            <Avatar rep={row.rep} size={22} />
                            {repName(row.rep)}
                          </span>
                          <div style={{ color: MUTED, fontSize: 12 }}>{row.deals} open deals</div>
                        </td>
                        <td style={{ padding: 6 }}>{money(row.open)}</td>
                        <td style={{ padding: 6, color: MUTED }}>{money(row.weighted)}</td>
                        <td style={{ padding: 6, fontWeight: 700 }}>{money(row.won)}</td>
                        <td style={{ padding: 6, color: MUTED }}>{row.target ? money(row.target) : '—'}</td>
                        <td style={{ padding: 6 }}>
                          {row.percent === null ? <span style={{ color: MUTED }}>—</span> : (
                            <>
                              <div style={{ fontSize: 12, color: MUTED, marginBottom: 3 }}>{row.percent}%</div>
                              <ProgressBar percent={row.percent} color={row.percent >= 100 ? WON : ACCENT} />
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card>
              <SectionTitle>Deals closing this quarter</SectionTitle>
              {inQuarter.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No deal closes in this quarter.</p>}
              {inQuarter.map((deal) => (
                <a
                  key={deal.id}
                  href={`#/admin/opportunity/${deal.id}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: INK,
                    padding: '8px 0', borderTop: `1px solid ${BORDER}`, fontSize: 14,
                  }}
                >
                  <StageBadge stage={deal.state} outcome={deal.outcome} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {deal.name}
                    <span style={{ color: MUTED }}> · {deal.account?.name}</span>
                  </span>
                  <span style={{ color: MUTED, fontSize: 12 }}>{repName(deal.owner)}</span>
                  <span style={{ color: MUTED, fontSize: 12 }}>{deal.close_date}</span>
                  <strong style={{ whiteSpace: 'nowrap' }}>{money(deal.amount)}</strong>
                </a>
              ))}
            </Card>
          </div>

          <div style={{ display: 'grid', gap: 20 }}>
            <Card>
              <SectionTitle>Win / loss</SectionTitle>
              <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: MUTED }}>Won</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: WON }}>{money(sum(won, 'amount'))}</div>
                  <div style={{ fontSize: 12, color: MUTED }}>{won.length} deals</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: MUTED }}>Lost</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: LOST }}>{money(sum(lost, 'amount'))}</div>
                  <div style={{ fontSize: 12, color: MUTED }}>{lost.length} deals</div>
                </div>
              </div>
              {winRate !== null && <ProgressBar percent={winRate} color={WON} />}
              {byLossReason.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: MUTED, marginBottom: 6 }}>WHY WE LOST</div>
                  {byLossReason.map(({ reason, rows }) => (
                    <div key={reason} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '3px 0' }}>
                      <span style={{ flex: 1 }}>{LOSS_REASON_LABELS[reason]}</span>
                      <span style={{ color: MUTED }}>{rows.length}</span>
                      <strong>{money(sum(rows, 'amount'))}</strong>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <SectionTitle>Open pipeline by source</SectionTitle>
              {bySource.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>Nothing open in this quarter.</p>}
              {bySource.map(({ source, rows, amount }) => (
                <div key={source} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '5px 0', borderTop: `1px solid ${BORDER}` }}>
                  <span style={{ flex: 1 }}>{source.replace(/_/g, ' ')}</span>
                  <span style={{ color: MUTED }}>{number(rows.length)}</span>
                  <strong>{money(amount)}</strong>
                </div>
              ))}
            </Card>

            <Card>
              <SectionTitle>Stage mix</SectionTitle>
              {Object.keys(STAGE_LABELS).filter((stage) => stage !== 'closed').map((stage) => {
                const rows = open.filter((deal) => deal.state === stage);
                if (!rows.length) return null;
                return (
                  <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '5px 0', borderTop: `1px solid ${BORDER}` }}>
                    <span style={{ flex: 1 }}>{STAGE_LABELS[stage]}</span>
                    <span style={{ color: MUTED }}>{rows.length}</span>
                    <strong>{money(sum(rows, 'amount'))}</strong>
                  </div>
                );
              })}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, hint, children }) {
  return (
    <Card>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, color: MUTED, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, margin: '4px 0 2px' }}>{value}</div>
      <div style={{ color: MUTED, fontSize: 12 }}>{hint}</div>
      {children}
    </Card>
  );
}
