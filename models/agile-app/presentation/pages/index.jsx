import React, { useEffect, useState } from 'react';
import { supabaseClient } from '../../supabaseClient';
import { useRequireSession, getProfile, signOut } from '../lib';

// ---------------------------------------------------------------------------
// Agile portal home — "Your work", the page a team member lands on. The whole
// portal is private: this page redirects to /signin when there is no session.
// It shows the issues assigned to the signed-in member, the sprints currently
// running and the project list, and links the three working pages (board,
// backlog, reports) plus the generated backoffice.
//
// This file also owns the shared look of the portal (palette, issue type and
// priority marks, state colours) and the top navigation, which the /priv pages
// import from here — same convention as intranet-app.
// ---------------------------------------------------------------------------

export const ACCENT = '#0c66e4';
export const ACCENT_SOFT = '#e9f2ff';
export const INK = '#172b4d';
export const MUTED = '#626f86';
export const BORDER = '#dfe1e6';
export const BG_SOFT = '#f7f8f9';
export const SURFACE = '#ffffff';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// Workflow states of the issue concept, in workflow order — the board columns.
export const ISSUE_STATES = ['backlog', 'todo', 'in_progress', 'in_review', 'done'];
export const STATE_LABELS = {
  backlog: 'Backlog', todo: 'To do', in_progress: 'In progress',
  in_review: 'In review', done: 'Done',
};
export const STATE_COLORS = {
  backlog: '#8993a4', todo: '#42526e', in_progress: '#0c66e4',
  in_review: '#8b5cf6', done: '#22a06b',
  // sprint workflow
  planned: '#8993a4', active: '#0c66e4', completed: '#22a06b',
};

// Issue types and priorities render as the small coloured marks Jira users read
// at a glance on a card, without pulling in an icon dependency.
export const TYPE_MARK = {
  epic: { symbol: '◈', color: '#8b5cf6', label: 'Epic' },
  story: { symbol: '▢', color: '#22a06b', label: 'Story' },
  task: { symbol: '✓', color: '#0c66e4', label: 'Task' },
  bug: { symbol: '●', color: '#e2483d', label: 'Bug' },
  subtask: { symbol: '▸', color: '#5e6c84', label: 'Subtask' },
};
export const PRIORITY_MARK = {
  highest: { symbol: '⏫', color: '#c9372c', label: 'Highest' },
  high: { symbol: '🔺', color: '#e2483d', label: 'High' },
  medium: { symbol: '⏺', color: '#e2b203', label: 'Medium' },
  low: { symbol: '🔻', color: '#1f845a', label: 'Low' },
  lowest: { symbol: '⏬', color: '#4bce97', label: 'Lowest' },
};

export const memberName = (member) => (member ? `${member.first_name} ${member.last_name}` : 'Unassigned');
export const initials = (member) => (member ? `${member.first_name[0] ?? ''}${member.last_name[0] ?? ''}`.toUpperCase() : '–');

export function TypeMark({ type }) {
  const mark = TYPE_MARK[type] ?? TYPE_MARK.task;
  return <span title={mark.label} style={{ color: mark.color, fontSize: 13 }}>{mark.symbol}</span>;
}

export function PriorityMark({ priority }) {
  const mark = PRIORITY_MARK[priority] ?? PRIORITY_MARK.medium;
  return <span title={`Priority: ${mark.label}`} style={{ fontSize: 11 }}>{mark.symbol}</span>;
}

export function StateBadge({ state }) {
  const color = STATE_COLORS[state] ?? MUTED;
  return (
    <span style={{
      background: `${color}1f`, color, borderRadius: 3, padding: '2px 7px',
      fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.3,
      whiteSpace: 'nowrap',
    }}>
      {STATE_LABELS[state] ?? state}
    </span>
  );
}

export function Avatar({ member, size = 24 }) {
  return (
    <span
      title={memberName(member)}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: size, height: size, borderRadius: '50%', flexShrink: 0,
        background: member ? ACCENT_SOFT : '#ebecf0', color: member ? ACCENT : MUTED,
        fontSize: size * 0.42, fontWeight: 700, border: `1px solid ${BORDER}`,
      }}
    >
      {initials(member)}
    </span>
  );
}

// Top navigation shared by every portal page.
export function Nav({ current, session }) {
  const links = [
    { href: '#/', label: 'Your work', key: 'home' },
    { href: '#/priv/board', label: 'Board', key: 'board' },
    { href: '#/priv/backlog', label: 'Backlog', key: 'backlog' },
    { href: '#/priv/reports', label: 'Reports', key: 'reports' },
  ];
  return (
    <header style={{
      background: SURFACE, borderBottom: `1px solid ${BORDER}`, position: 'sticky',
      top: 0, zIndex: 30,
    }}>
      <div style={{
        maxWidth: 1400, margin: '0 auto', padding: '0 20px', display: 'flex',
        alignItems: 'center', gap: 20, height: 52,
      }}>
        <a href="#/" style={{ textDecoration: 'none', color: INK, fontWeight: 800, fontSize: 17, letterSpacing: -0.3 }}>
          <span style={{ color: ACCENT }}>◆</span> Agile Kit
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

// The columns every page needs to render an issue row or card.
export const ISSUE_SELECT =
  'id, id_presentation, summary, type, priority, state, story_points, rank, epic, '
  + 'project(id, key, name), assignee(id, first_name, last_name), '
  + 'sprint(id, name, state, project(id, key, name)), '
  + 'issue_label(label(id, name, color))';

export const issueLabels = (issue) => (issue.issue_label ?? []).map((row) => row.label).filter(Boolean);

export default function PortalHome() {
  const session = useRequireSession(); // redirects to /signin when signed out
  const [me, setMe] = useState(undefined); // undefined = loading, null = no profile row
  const [myIssues, setMyIssues] = useState(null);
  const [sprints, setSprints] = useState(null);
  const [sprintIssues, setSprintIssues] = useState([]);
  const [projects, setProjects] = useState([]);

  useEffect(() => {
    if (!session) return;
    getProfile().then((profile) => setMe(profile?.record ?? null));
    supabaseClient
      .from('project')
      .select('id, key, name, type, issue_count, open_points, is_archived, lead(first_name, last_name)')
      .eq('is_archived', false)
      .order('key')
      .then(({ data }) => setProjects(data ?? []));
    supabaseClient
      .from('sprint')
      .select('id, name, goal, start_date, end_date, capacity_points, state, project(id, key, name)')
      .eq('state', 'active')
      .then(({ data }) => setSprints(data ?? []));
  }, [session]);

  // Issues of the running sprints, to draw their progress bars.
  useEffect(() => {
    if (!sprints?.length) return;
    supabaseClient
      .from('issue')
      .select('id, state, story_points, sprint')
      .in('sprint', sprints.map((sprint) => sprint.id))
      .then(({ data }) => setSprintIssues(data ?? []));
  }, [sprints]);

  useEffect(() => {
    if (!me) {
      if (me === null) setMyIssues([]);
      return;
    }
    supabaseClient
      .from('issue')
      .select(ISSUE_SELECT)
      .eq('assignee', me.id)
      .neq('state', 'done')
      .order('rank')
      .then(({ data }) => setMyIssues(data ?? []));
  }, [me]);

  const byState = (state) => (myIssues ?? []).filter((issue) => issue.state === state);

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="home" session={session} />
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '24px 20px 60px' }}>
        <h1 style={{ fontSize: 24, margin: '0 0 4px' }}>
          {me ? `Hello, ${me.first_name}` : 'Your work'}
        </h1>
        <p style={{ color: MUTED, margin: '0 0 24px', fontSize: 14 }}>
          {me === null
            ? 'This account has no team member profile, so no issues are assigned to it. You can still browse every board and project.'
            : 'Everything assigned to you that is not done yet.'}
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(280px, 1fr)', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'grid', gap: 20 }}>
            <Card>
              <SectionTitle>Assigned to me</SectionTitle>
              {myIssues === null && <p style={{ color: MUTED, fontSize: 14 }}>Loading…</p>}
              {myIssues?.length === 0 && (
                <p style={{ color: MUTED, fontSize: 14 }}>Nothing assigned right now. Pick something up from the <a href="#/priv/board" style={{ color: ACCENT }}>board</a>.</p>
              )}
              {ISSUE_STATES.filter((state) => state !== 'done').map((state) => {
                const issues = byState(state);
                if (!issues.length) return null;
                return (
                  <div key={state} style={{ marginBottom: 14 }}>
                    <div style={{ marginBottom: 6 }}><StateBadge state={state} /></div>
                    {issues.map((issue) => <IssueRow key={issue.id} issue={issue} />)}
                  </div>
                );
              })}
            </Card>

            <Card>
              <SectionTitle>Running sprints</SectionTitle>
              {sprints === null && <p style={{ color: MUTED, fontSize: 14 }}>Loading…</p>}
              {sprints?.length === 0 && <p style={{ color: MUTED, fontSize: 14 }}>No sprint is active.</p>}
              {sprints?.map((sprint) => {
                const issues = sprintIssues.filter((issue) => issue.sprint === sprint.id);
                const total = issues.reduce((sum, issue) => sum + Number(issue.story_points ?? 0), 0);
                const done = issues
                  .filter((issue) => issue.state === 'done')
                  .reduce((sum, issue) => sum + Number(issue.story_points ?? 0), 0);
                const percent = total ? Math.round((done / total) * 100) : 0;
                return (
                  <div key={sprint.id} style={{ padding: '10px 0', borderTop: `1px solid ${BORDER}` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                      <strong style={{ fontSize: 14 }}>{sprint.project?.key} · {sprint.name}</strong>
                      <span style={{ color: MUTED, fontSize: 13 }}>
                        {sprint.start_date} → {sprint.end_date}
                      </span>
                    </div>
                    {sprint.goal && <div style={{ color: MUTED, fontSize: 13, margin: '2px 0 8px' }}>{sprint.goal}</div>}
                    <ProgressBar percent={percent} />
                    <div style={{ color: MUTED, fontSize: 12, marginTop: 4 }}>
                      {done} of {total} points done · {issues.length} issues · capacity {sprint.capacity_points ?? '—'}
                    </div>
                  </div>
                );
              })}
            </Card>
          </div>

          <Card>
            <SectionTitle>Projects</SectionTitle>
            {projects.map((project) => (
              <a
                key={project.id}
                href={`#/priv/board?project=${project.id}`}
                style={{
                  display: 'block', textDecoration: 'none', color: INK,
                  padding: '10px 0', borderTop: `1px solid ${BORDER}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    background: ACCENT_SOFT, color: ACCENT, borderRadius: 3, padding: '1px 6px',
                    fontSize: 12, fontWeight: 800,
                  }}>{project.key}</span>
                  <strong style={{ fontSize: 14 }}>{project.name}</strong>
                </div>
                <div style={{ color: MUTED, fontSize: 12, marginTop: 3 }}>
                  {project.type} · {project.issue_count ?? 0} issues · {project.open_points ?? 0} points open
                  {project.lead && ` · lead ${memberName(project.lead)}`}
                </div>
              </a>
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <h2 style={{
      fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, color: MUTED,
      margin: '0 0 10px', fontWeight: 700,
    }}>
      {children}
    </h2>
  );
}

export function ProgressBar({ percent, color = ACCENT }) {
  return (
    <div style={{ background: '#ebecf0', borderRadius: 3, height: 8, overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(100, Math.max(0, percent))}%`, background: color, height: '100%' }} />
    </div>
  );
}

function IssueRow({ issue }) {
  return (
    <a
      href={`#/admin/issue/${issue.id}`}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', color: INK,
        padding: '6px 0', fontSize: 14,
      }}
    >
      <TypeMark type={issue.type} />
      <span style={{ fontWeight: 700, color: ACCENT, minWidth: 74 }}>{issue.id_presentation}</span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {issue.summary}
      </span>
      <PriorityMark priority={issue.priority} />
      {issue.story_points != null && (
        <span style={{
          background: '#ebecf0', color: MUTED, borderRadius: 10, padding: '1px 8px',
          fontSize: 11, fontWeight: 700,
        }}>{issue.story_points}</span>
      )}
    </a>
  );
}
