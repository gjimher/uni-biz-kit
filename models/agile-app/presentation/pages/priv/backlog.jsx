import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { supabaseClient } from '../../../supabaseClient';
import { useRequireSession, getPermissions, transition } from '../../lib';
import { Select, inputStyle } from './board.jsx';
import {
  Nav, Avatar, TypeMark, PriorityMark, StateBadge, ProgressBar,
  ISSUE_SELECT,
  ACCENT, ACCENT_SOFT, INK, MUTED, BORDER, BG_SOFT, SURFACE, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/backlog — sprint planning. The open sprints of a project sit on top,
// the unscheduled backlog below; dragging an issue between them writes
// issue.sprint, which is all a sprint membership is. Sprint start/complete go
// through the same workflow-transition function as the board, so the sprint
// rules apply (a sprint cannot start without dates).
//
// issue.sprint is a plain relation, so an issue may be scheduled into another
// project's sprint (a shared work stream). Those sprints get their own sections
// so the issues are neither hidden nor mistaken for unplanned backlog.
//
// The quick-add row creates an issue directly in the backlog state, the way
// a refinement session fills a backlog.
// ---------------------------------------------------------------------------

export default function BacklogPage() {
  const session = useRequireSession();
  const [searchParams, setSearchParams] = useSearchParams();

  const [projects, setProjects] = useState([]);
  const [sprints, setSprints] = useState([]);
  const [issues, setIssues] = useState(null);
  const [canWrite, setCanWrite] = useState(false);
  const [canPlan, setCanPlan] = useState(false);
  const [dragging, setDragging] = useState(null);
  const [hoverTarget, setHoverTarget] = useState(null);
  const [error, setError] = useState('');
  const [newSummary, setNewSummary] = useState('');
  const [newType, setNewType] = useState('story');

  const projectId = searchParams.get('project') ? Number(searchParams.get('project')) : null;

  useEffect(() => {
    if (!session) return;
    getPermissions().then((permissions) => {
      setCanWrite((permissions?.issue ?? []).includes('write'));
      setCanPlan((permissions?.sprint ?? []).includes('write'));
    });
    supabaseClient
      .from('project')
      .select('id, key, name, type')
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
      .select('id, name, goal, start_date, end_date, capacity_points, state')
      .eq('project', projectId)
      .neq('state', 'completed')
      .order('start_date')
      .then(({ data }) => setSprints(data ?? []));
    supabaseClient
      .from('issue')
      .select(ISSUE_SELECT)
      .eq('project', projectId)
      .neq('state', 'done')
      .order('rank')
      .order('id')
      .then(({ data }) => setIssues(data ?? []));
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const project = projects.find((candidate) => candidate.id === projectId) ?? null;
  const backlogIssues = useMemo(
    () => (issues ?? []).filter((issue) => !issue.sprint || issue.sprint.state === 'completed'),
    [issues],
  );
  const externalSprints = useMemo(() => {
    const grouped = new Map();
    for (const issue of issues ?? []) {
      const sprint = issue.sprint;
      if (!sprint || sprint.state === 'completed' || sprint.project?.id === projectId) continue;
      if (!grouped.has(sprint.id)) grouped.set(sprint.id, { sprint, issues: [] });
      grouped.get(sprint.id).issues.push(issue);
    }
    return [...grouped.values()];
  }, [issues, projectId]);

  // The dragged issue is read back from the drag payload rather than only from
  // component state, so a drop is handled correctly even when the browser fires
  // dragstart and drop without a render in between.
  async function moveToSprint(event, sprintId) {
    const droppedId = Number(event.dataTransfer?.getData('text/plain'));
    const issue = dragging ?? (issues ?? []).find((candidate) => candidate.id === droppedId);
    setDragging(null);
    setHoverTarget(null);
    if (!issue) return;
    if (!canWrite) {
      setError('Your role can read the backlog but not schedule issues.');
      return;
    }
    if ((issue.sprint?.id ?? null) === sprintId) return;
    setError('');
    const { error: updateError } = await supabaseClient
      .from('issue')
      .update({ sprint: sprintId })
      .eq('id', issue.id);
    if (updateError) setError(updateError.message);
    load();
  }

  async function moveSprint(sprint, toState) {
    setError('');
    try {
      await transition('sprint', sprint.id, toState);
    } catch (transitionError) {
      setError(transitionError.message);
    }
    load();
  }

  async function addIssue(event) {
    event.preventDefault();
    if (!newSummary.trim() || !projectId) return;
    setError('');
    const { error: insertError } = await supabaseClient
      .from('issue')
      .insert({ project: projectId, summary: newSummary.trim(), type: newType });
    if (insertError) setError(insertError.message);
    setNewSummary('');
    load();
  }

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="backlog" session={session} />
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '18px 20px 60px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
          <h1 style={{ fontSize: 22, margin: 0 }}>Backlog</h1>
          <Select
            value={projectId ?? ''}
            onChange={(value) => setSearchParams({ project: value })}
            options={projects.map((item) => ({ value: item.id, label: `${item.key} · ${item.name}` }))}
          />
          {project && <span style={{ color: MUTED, fontSize: 13 }}>{project.type} project</span>}
        </div>

        {error && (
          <div style={{
            background: '#ffecea', border: '1px solid #f5b2ac', color: '#ae2a19',
            borderRadius: 6, padding: '9px 12px', fontSize: 14, marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        {issues === null && <p style={{ color: MUTED }}>Loading…</p>}

        {sprints.map((sprint) => {
          const sprintIssues = (issues ?? []).filter((issue) => issue.sprint?.id === sprint.id);
          const points = sprintIssues.reduce((sum, issue) => sum + Number(issue.story_points ?? 0), 0);
          const capacity = Number(sprint.capacity_points ?? 0);
          const percent = capacity ? Math.round((points / capacity) * 100) : 0;
          return (
            <Section
              key={sprint.id}
              highlighted={hoverTarget === sprint.id}
              onDragOver={(event) => { event.preventDefault(); setHoverTarget(sprint.id); }}
              onDrop={(event) => { event.preventDefault(); moveToSprint(event, sprint.id); }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 15 }}>{sprint.name}</strong>
                <StateBadge state={sprint.state} />
                <span style={{ color: MUTED, fontSize: 13 }}>
                  {sprint.start_date ?? '—'} → {sprint.end_date ?? '—'}
                </span>
                <span style={{ color: MUTED, fontSize: 13 }}>
                  {sprintIssues.length} issues · {points} of {capacity || '—'} points
                </span>
                <span style={{ flex: 1 }} />
                {canPlan && sprint.state === 'planned' && (
                  <Button onClick={() => moveSprint(sprint, 'active')}>Start sprint</Button>
                )}
                {canPlan && sprint.state === 'active' && (
                  <Button onClick={() => moveSprint(sprint, 'completed')}>Complete sprint</Button>
                )}
              </div>
              {sprint.goal && <div style={{ color: MUTED, fontSize: 13, marginTop: 4 }}>{sprint.goal}</div>}
              {capacity > 0 && (
                <div style={{ margin: '8px 0 4px' }}>
                  <ProgressBar percent={percent} color={points > capacity ? '#e2483d' : ACCENT} />
                </div>
              )}
              <IssueList issues={sprintIssues} setDragging={setDragging} draggable={canWrite} />
              {sprintIssues.length === 0 && <Empty>Drag issues here to plan them into this sprint.</Empty>}
            </Section>
          );
        })}

        {externalSprints.map(({ sprint, issues: sprintIssues }) => {
          const points = sprintIssues.reduce((sum, issue) => sum + Number(issue.story_points ?? 0), 0);
          const sprintProject = sprint.project;
          return (
            <Section
              key={`external-${sprint.id}`}
              highlighted={hoverTarget === sprint.id}
              onDragOver={(event) => { event.preventDefault(); setHoverTarget(sprint.id); }}
              onDrop={(event) => { event.preventDefault(); moveToSprint(event, sprint.id); }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 15 }}>
                  {sprintProject?.key ? `${sprintProject.key} · ` : ''}{sprint.name}
                </strong>
                <StateBadge state={sprint.state} />
                <span style={{ color: MUTED, fontSize: 13 }}>
                  other project · {sprintIssues.length} issues · {points} points
                </span>
              </div>
              <IssueList issues={sprintIssues} setDragging={setDragging} draggable={canWrite} />
            </Section>
          );
        })}

        <Section
          highlighted={hoverTarget === 'backlog'}
          onDragOver={(event) => { event.preventDefault(); setHoverTarget('backlog'); }}
          onDrop={(event) => { event.preventDefault(); moveToSprint(event, null); }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <strong style={{ fontSize: 15 }}>Backlog</strong>
            <span style={{ color: MUTED, fontSize: 13 }}>
              {backlogIssues.length} issues ·{' '}
              {backlogIssues.reduce((sum, issue) => sum + Number(issue.story_points ?? 0), 0)} points
            </span>
          </div>
          <IssueList issues={backlogIssues} setDragging={setDragging} draggable={canWrite} />
          {backlogIssues.length === 0 && <Empty>The backlog is empty.</Empty>}

          {canWrite && (
            <form onSubmit={addIssue} style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <Select
                value={newType}
                onChange={setNewType}
                options={['story', 'task', 'bug', 'epic', 'subtask'].map((item) => ({ value: item, label: item }))}
              />
              <input
                value={newSummary}
                onChange={(event) => setNewSummary(event.target.value)}
                placeholder="What needs doing?"
                style={{ ...inputStyle, flex: 1, minWidth: 240 }}
              />
              <Button type="submit">Add to backlog</Button>
            </form>
          )}
        </Section>
      </div>
    </div>
  );
}

function Section({ children, highlighted, ...handlers }) {
  return (
    <div
      {...handlers}
      style={{
        background: highlighted ? ACCENT_SOFT : SURFACE,
        border: `1px solid ${highlighted ? ACCENT : BORDER}`,
        borderRadius: 8, padding: '14px 16px', marginBottom: 16,
      }}
    >
      {children}
    </div>
  );
}

function IssueList({ issues, setDragging, draggable }) {
  return (
    <div style={{ marginTop: 8 }}>
      {issues.map((issue) => (
        <div
          key={issue.id}
          draggable={draggable}
          onDragStart={(event) => {
            event.dataTransfer.setData('text/plain', String(issue.id));
            event.dataTransfer.effectAllowed = 'move';
            setDragging(issue);
          }}
          onDragEnd={() => setDragging(null)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px',
            borderTop: `1px solid ${BORDER}`, fontSize: 14,
            cursor: draggable ? 'grab' : 'default', background: SURFACE,
          }}
        >
          <TypeMark type={issue.type} />
          <a
            href={`#/admin/issue/${issue.id}`}
            style={{ color: ACCENT, fontWeight: 700, textDecoration: 'none', minWidth: 74 }}
          >
            {issue.id_presentation}
          </a>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {issue.summary}
          </span>
          <StateBadge state={issue.state} />
          <PriorityMark priority={issue.priority} />
          {issue.story_points != null && (
            <span style={{
              background: '#ebecf0', color: MUTED, borderRadius: 10, padding: '1px 8px',
              fontSize: 11, fontWeight: 700,
            }}>{issue.story_points}</span>
          )}
          <Avatar member={issue.assignee} size={22} />
        </div>
      ))}
    </div>
  );
}

function Empty({ children }) {
  return <p style={{ color: MUTED, fontSize: 13, margin: '10px 0 2px' }}>{children}</p>;
}

function Button({ children, ...props }) {
  return (
    <button
      {...props}
      style={{
        background: ACCENT, color: '#fff', border: 'none', borderRadius: 4,
        padding: '6px 12px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}
