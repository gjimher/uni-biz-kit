import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { supabaseClient } from '../../../supabaseClient';
import { useRequireSession } from '../../lib';
import { Select } from './board.jsx';
import {
  Nav, Card, STATE_LABELS, STATE_COLORS, ISSUE_STATES, TYPE_MARK,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, SURFACE, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/reports — the three numbers a team actually looks at: how much work each
// sprint committed to versus finished (velocity), what the work is made of (by
// type), and where the open work currently sits (by state).
//
// Charts are plain SVG: two series get a legend and their own validated hues,
// single-series charts are direct-labelled and need none. Everything is drawn
// from the issues themselves — there is no reporting table in the model.
// ---------------------------------------------------------------------------

// Two-series categorical pair, checked for colour-vision separation against a
// light surface (deutan ΔE 26.1, normal ΔE 27.7, contrast >= 3:1).
const SERIES_COMMITTED = '#0c66e4';
const SERIES_COMPLETED = '#22a06b';
const TRACK = '#ebecf0';

export default function ReportsPage() {
  const session = useRequireSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState([]);
  const [sprints, setSprints] = useState([]);
  const [issues, setIssues] = useState(null);

  const projectId = searchParams.get('project') ? Number(searchParams.get('project')) : null;

  useEffect(() => {
    if (!session) return;
    supabaseClient
      .from('project')
      .select('id, key, name')
      .eq('is_archived', false)
      .order('key')
      .then(({ data }) => setProjects(data ?? []));
  }, [session]);

  useEffect(() => {
    if (!projects.length || projectId) return;
    setSearchParams({ project: String(projects[0].id) }, { replace: true });
  }, [projects, projectId, setSearchParams]);

  const load = useCallback(() => {
    if (!projectId) return;
    supabaseClient
      .from('sprint')
      .select('id, name, state, start_date, capacity_points')
      .eq('project', projectId)
      .order('start_date')
      .then(({ data }) => setSprints(data ?? []));
    supabaseClient
      .from('issue')
      .select('id, type, state, story_points, sprint, logged_hours')
      .eq('project', projectId)
      .then(({ data }) => setIssues(data ?? []));
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const rows = issues ?? [];
  const points = (list) => list.reduce((sum, issue) => sum + Number(issue.story_points ?? 0), 0);

  const velocity = useMemo(() => sprints.map((sprint) => {
    const sprintIssues = rows.filter((issue) => issue.sprint === sprint.id);
    return {
      label: sprint.name,
      state: sprint.state,
      committed: points(sprintIssues),
      completed: points(sprintIssues.filter((issue) => issue.state === 'done')),
    };
  }), [sprints, rows]);

  const byType = useMemo(() => Object.keys(TYPE_MARK)
    .map((type) => ({ key: type, label: type, value: rows.filter((issue) => issue.type === type).length }))
    .filter((row) => row.value > 0), [rows]);

  const byState = useMemo(() => ISSUE_STATES
    .map((state) => ({
      key: state,
      label: STATE_LABELS[state],
      value: rows.filter((issue) => issue.state === state).length,
      color: STATE_COLORS[state],
    }))
    .filter((row) => row.value > 0), [rows]);

  const completedSprints = velocity.filter((row) => row.state === 'completed');
  const averageVelocity = completedSprints.length
    ? Math.round(completedSprints.reduce((sum, row) => sum + row.completed, 0) / completedSprints.length)
    : null;
  const openPoints = points(rows.filter((issue) => issue.state !== 'done'));
  const loggedHours = rows.reduce((sum, issue) => sum + Number(issue.logged_hours ?? 0), 0);

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="reports" session={session} />
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '18px 20px 60px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <h1 style={{ fontSize: 22, margin: 0 }}>Reports</h1>
          <Select
            value={projectId ?? ''}
            onChange={(value) => setSearchParams({ project: value })}
            options={projects.map((item) => ({ value: item.id, label: `${item.key} · ${item.name}` }))}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 18 }}>
          <StatTile label="Issues" value={rows.length} />
          <StatTile label="Open story points" value={openPoints} />
          <StatTile label="Average velocity" value={averageVelocity ?? '—'} hint="points per completed sprint" />
          <StatTile label="Hours logged" value={loggedHours} />
        </div>

        <Card style={{ marginBottom: 18 }}>
          <ChartTitle>Velocity — committed vs completed story points</ChartTitle>
          {velocity.length === 0
            ? <Empty />
            : <>
              <Legend items={[
                { label: 'Committed', color: SERIES_COMMITTED },
                { label: 'Completed', color: SERIES_COMPLETED },
              ]} />
              <VelocityChart data={velocity} />
            </>}
        </Card>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18 }}>
          <Card>
            <ChartTitle>Issues by type</ChartTitle>
            {byType.length === 0 ? <Empty /> : <BarList data={byType.map((row) => ({ ...row, color: TYPE_MARK[row.key].color }))} />}
          </Card>
          <Card>
            <ChartTitle>Issues by state</ChartTitle>
            {byState.length === 0 ? <Empty /> : <BarList data={byState} />}
          </Card>
        </div>
      </div>
    </div>
  );
}

function ChartTitle({ children }) {
  return <h2 style={{ fontSize: 14, margin: '0 0 10px', fontWeight: 700 }}>{children}</h2>;
}

function Empty() {
  return <p style={{ color: MUTED, fontSize: 13, margin: 0 }}>Not enough data yet.</p>;
}

function StatTile({ label, value, hint }) {
  return (
    <div style={{ background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 8, padding: '12px 14px' }}>
      <div style={{ fontSize: 12, color: MUTED, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1.2 }}>{value}</div>
      {hint && <div style={{ fontSize: 11, color: MUTED }}>{hint}</div>}
    </div>
  );
}

function Legend({ items }) {
  return (
    <div style={{ display: 'flex', gap: 14, marginBottom: 8 }}>
      {items.map((item) => (
        <span key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: MUTED }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: item.color, display: 'inline-block' }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

// Path for a bar with only its data end rounded, anchored to the baseline.
function barPath(x, y, width, height, radius) {
  const r = Math.min(radius, height, width / 2);
  if (height <= 0) return '';
  return `M${x},${y + height} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height} Z`;
}

function VelocityChart({ data }) {
  const height = 220;
  const padding = { top: 8, right: 8, bottom: 32, left: 34 };
  // Fixed pixel width (not a stretched viewBox): the bars keep their intended
  // thickness, the chart starts at the axis, and long sprint runs scroll.
  const width = Math.max(480, data.length * 120);
  const plotHeight = height - padding.top - padding.bottom;
  const max = Math.max(10, ...data.map((row) => Math.max(row.committed, row.completed)));
  const groupWidth = (width - padding.left - padding.right) / data.length;
  const barWidth = Math.min(20, (groupWidth - 10) / 2 - 1);
  const scale = (value) => (value / max) * plotHeight;
  const ticks = [0, max / 2, max];

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img"
        aria-label="Committed and completed story points per sprint">
        {ticks.map((tick) => {
          const y = padding.top + plotHeight - scale(tick);
          return (
            <g key={tick}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke={BORDER} strokeWidth="1" />
              <text x={padding.left - 6} y={y + 4} textAnchor="end" fontSize="10" fill={MUTED}>{Math.round(tick)}</text>
            </g>
          );
        })}
        {data.map((row, index) => {
          const groupX = padding.left + index * groupWidth;
          const centre = groupX + groupWidth / 2;
          // 2px surface gap between the two bars of a group
          const committedX = centre - barWidth - 1;
          const completedX = centre + 1;
          const committedHeight = scale(row.committed);
          const completedHeight = scale(row.completed);
          return (
            <g key={row.label}>
              <path
                d={barPath(committedX, padding.top + plotHeight - committedHeight, barWidth, committedHeight, 4)}
                fill={SERIES_COMMITTED}
              >
                <title>{`${row.label} — committed ${row.committed} points`}</title>
              </path>
              <path
                d={barPath(completedX, padding.top + plotHeight - completedHeight, barWidth, completedHeight, 4)}
                fill={SERIES_COMPLETED}
              >
                <title>{`${row.label} — completed ${row.completed} points`}</title>
              </path>
              <text x={centre} y={height - 16} textAnchor="middle" fontSize="11" fill={INK}>{row.label}</text>
              <text x={centre} y={height - 4} textAnchor="middle" fontSize="10" fill={MUTED}>{row.state}</text>
            </g>
          );
        })}
        <line
          x1={padding.left} x2={width - padding.right}
          y1={padding.top + plotHeight} y2={padding.top + plotHeight}
          stroke={MUTED} strokeWidth="1"
        />
      </svg>
    </div>
  );
}

// Single-series horizontal bars: every bar carries its own label and value, so
// colour is decoration here rather than the only way to tell the rows apart.
function BarList({ data }) {
  const max = Math.max(...data.map((row) => row.value), 1);
  return (
    <div>
      {data.map((row) => (
        <div key={row.key} style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '7px 0' }}>
          <span style={{ width: 82, fontSize: 12, color: MUTED, textTransform: 'capitalize' }}>{row.label}</span>
          <span style={{ flex: 1, background: TRACK, borderRadius: 4, height: 12, overflow: 'hidden' }}>
            <span
              title={`${row.label}: ${row.value}`}
              style={{
                display: 'block', width: `${(row.value / max) * 100}%`, height: '100%',
                background: row.color ?? ACCENT, borderRadius: 4,
              }}
            />
          </span>
          <span style={{ width: 26, textAlign: 'right', fontSize: 12, fontWeight: 700 }}>{row.value}</span>
        </div>
      ))}
    </div>
  );
}
