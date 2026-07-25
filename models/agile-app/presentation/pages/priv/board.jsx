import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { supabaseClient } from '../../../supabaseClient';
import { useRequireSession, getPermissions, transition } from '../../lib';
import {
  Nav, Avatar, TypeMark, PriorityMark, ISSUE_STATES, STATE_LABELS, STATE_COLORS,
  ISSUE_SELECT, issueLabels, memberName,
  ACCENT, INK, MUTED, BORDER, BG_SOFT, SURFACE, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/board — the kanban board. One column per issue workflow state; dropping
// a card on another column performs the real workflow transition through the
// generated `workflow-transition` backend function (lib/workflow.js), which
// re-checks state ownership and runs the transition rules — so a drop can be
// rejected (e.g. "Assign the issue before starting work on it") and the card
// snaps back. Dropping a card on another card only reorders it (issue.rank).
//
// The board record supplies the WIP limit and the swimlane grouping; a scrum
// board shows active sprints only, a kanban board the whole flow.
// ---------------------------------------------------------------------------

const columnHeaderStyle = {
  display: 'flex', alignItems: 'center', gap: 6, padding: '10px 12px 8px',
  fontSize: 12, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.5,
};

export default function BoardPage() {
  const session = useRequireSession();
  const [searchParams, setSearchParams] = useSearchParams();

  const [projects, setProjects] = useState([]);
  const [boards, setBoards] = useState([]);
  const [members, setMembers] = useState([]);
  const [epics, setEpics] = useState([]);
  const [issues, setIssues] = useState(null);
  const [canWrite, setCanWrite] = useState(false);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [dragging, setDragging] = useState(null);
  const [hover, setHover] = useState(null); // { state, beforeId }

  // Filters
  const [text, setText] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [sprintOnly, setSprintOnly] = useState(true);

  const projectId = searchParams.get('project') ? Number(searchParams.get('project')) : null;
  const boardId = searchParams.get('board') ? Number(searchParams.get('board')) : null;

  useEffect(() => {
    if (!session) return;
    getPermissions().then((permissions) => setCanWrite((permissions?.issue ?? []).includes('write')));
    supabaseClient
      .from('project')
      .select('id, key, name, type')
      .eq('is_archived', false)
      .order('key')
      .then(({ data }) => setProjects(data ?? []));
    supabaseClient
      .from('member')
      .select('id, first_name, last_name')
      .eq('is_active', true)
      .order('first_name')
      .then(({ data }) => setMembers(data ?? []));
    supabaseClient
      .from('board')
      .select('id, name, type, wip_limit, swimlane_by, is_default, project')
      .order('name')
      .then(({ data }) => setBoards(data ?? []));
    // Epics may belong to another project. Load their display values separately
    // so an explicitly cross-project epic still gets a useful swimlane label.
    supabaseClient
      .from('issue')
      .select('id, id_presentation, summary')
      .eq('type', 'epic')
      .order('id')
      .then(({ data }) => setEpics(data ?? []));
  }, [session]);

  // Default to the first project / its default board when nothing is selected.
  useEffect(() => {
    if (!projects.length || projectId) return;
    setSearchParams({ project: String(projects[0].id) }, { replace: true });
  }, [projects, projectId, setSearchParams]);

  const projectBoards = useMemo(
    () => boards.filter((board) => board.project === projectId),
    [boards, projectId],
  );
  const board = useMemo(
    () => projectBoards.find((candidate) => candidate.id === boardId)
      ?? projectBoards.find((candidate) => candidate.is_default)
      ?? projectBoards[0]
      ?? null,
    [projectBoards, boardId],
  );
  const project = projects.find((candidate) => candidate.id === projectId) ?? null;

  const loadIssues = useCallback(() => {
    if (!projectId) return;
    supabaseClient
      .from('issue')
      .select(ISSUE_SELECT)
      .eq('project', projectId)
      .order('rank')
      .order('id')
      .then(({ data, error: loadError }) => {
        if (loadError) setError(loadError.message);
        setIssues(data ?? []);
      });
  }, [projectId]);

  useEffect(() => { loadIssues(); }, [loadIssues]);

  const scrumMode = board?.type === 'scrum' && sprintOnly;

  // Board scope is independent of personal quick filters. WIP constraints apply
  // to every card in scope, including cards hidden by a search or assignee filter.
  const boardIssues = useMemo(() => (issues ?? []).filter((issue) => {
    if (scrumMode && issue.sprint?.state !== 'active') return false;
    return true;
  }), [issues, scrumMode]);

  const visibleIssues = useMemo(() => boardIssues.filter((issue) => {
    if (assigneeFilter && String(issue.assignee?.id ?? '') !== assigneeFilter) return false;
    if (typeFilter && issue.type !== typeFilter) return false;
    if (text) {
      const haystack = `${issue.id_presentation} ${issue.summary}`.toLowerCase();
      if (!haystack.includes(text.toLowerCase())) return false;
    }
    return true;
  }), [boardIssues, assigneeFilter, typeFilter, text]);

  // Swimlanes: [{ key, label, issues }] — a single unnamed lane when grouping is off.
  const lanes = useMemo(() => {
    const groupBy = board?.swimlane_by ?? 'none';
    if (groupBy === 'none') return [{ key: 'all', label: null, issues: visibleIssues }];

    const laneOf = (issue) => {
      if (groupBy === 'assignee') return issue.assignee ? { key: `m${issue.assignee.id}`, label: memberName(issue.assignee) } : { key: 'none', label: 'Unassigned' };
      if (groupBy === 'priority') return { key: issue.priority, label: `Priority: ${issue.priority}` };
      return issue.epic ? { key: `e${issue.epic}`, label: epicLabel(epics, issue.epic) } : { key: 'none', label: 'No epic' };
    };
    const map = new Map();
    for (const issue of visibleIssues) {
      const lane = laneOf(issue);
      if (!map.has(lane.key)) map.set(lane.key, { ...lane, issues: [] });
      map.get(lane.key).issues.push(issue);
    }
    const ordered = [...map.values()];
    if (groupBy === 'priority') {
      const order = ['highest', 'high', 'medium', 'low', 'lowest'];
      ordered.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    }
    return ordered;
  }, [board, visibleIssues, epics]);

  const inProgressCount = boardIssues.filter((issue) => issue.state === 'in_progress').length;
  const wipExceeded = Boolean(board?.wip_limit) && inProgressCount > board.wip_limit;

  // A drop either moves the card to another column (workflow transition) or
  // reorders it inside one (rank). Both end with a reload so the board shows
  // exactly what the backend accepted.
  //
  // The dragged issue is read back from the drag payload rather than only from
  // component state, so a drop is handled correctly even when the browser fires
  // dragstart and drop without a render in between.
  async function handleDrop(event, toState, beforeIssue) {
    const droppedId = Number(event.dataTransfer?.getData('text/plain'));
    const issue = dragging ?? (issues ?? []).find((candidate) => candidate.id === droppedId);
    setHover(null);
    setDragging(null);
    if (!issue) return;
    if (!canWrite) {
      setError('Your role can read the board but not move issues.');
      return;
    }
    if (issue.state === toState && !beforeIssue) return;

    setBusyId(issue.id);
    setError('');
    try {
      if (issue.state !== toState) {
        await transition('issue', issue.id, toState);
      }
      const rank = rankForDrop(boardIssues, issue, toState, beforeIssue);
      if (rank != null) {
        const { error: rankError } = await supabaseClient
          .from('issue')
          .update({ rank })
          .eq('id', issue.id);
        if (rankError) throw new Error(rankError.message);
      }
    } catch (dropError) {
      setError(dropError.message);
    } finally {
      setBusyId(null);
      loadIssues();
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <Nav current="board" session={session} />
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: '18px 20px 40px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
          <h1 style={{ fontSize: 22, margin: 0 }}>{board ? board.name : 'Board'}</h1>
          {project && <span style={{ color: MUTED, fontSize: 14 }}>{project.key} · {project.name}</span>}
          {board?.type === 'scrum' && (
            <span style={{ color: MUTED, fontSize: 13 }}>
              {sprintOnly ? 'active sprints only' : 'all issues'}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
          <Select
            value={projectId ?? ''}
            onChange={(value) => setSearchParams({ project: value })}
            options={projects.map((item) => ({ value: item.id, label: `${item.key} · ${item.name}` }))}
          />
          {projectBoards.length > 1 && (
            <Select
              value={board?.id ?? ''}
              onChange={(value) => setSearchParams({ project: String(projectId), board: value })}
              options={projectBoards.map((item) => ({ value: item.id, label: item.name }))}
            />
          )}
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Search board…"
            style={inputStyle}
          />
          <Select
            value={assigneeFilter}
            onChange={setAssigneeFilter}
            placeholder="All assignees"
            options={members.map((item) => ({ value: item.id, label: memberName(item) }))}
          />
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            placeholder="All types"
            options={['epic', 'story', 'task', 'bug', 'subtask'].map((item) => ({ value: item, label: item }))}
          />
          {board?.type === 'scrum' && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: MUTED }}>
              <input type="checkbox" checked={sprintOnly} onChange={(event) => setSprintOnly(event.target.checked)} />
              Active sprints only
            </label>
          )}
          {board?.swimlane_by && board.swimlane_by !== 'none' && (
            <span style={{ fontSize: 13, color: MUTED }}>swimlanes: {board.swimlane_by}</span>
          )}
        </div>

        {error && (
          <div style={{
            background: '#ffecea', border: '1px solid #f5b2ac', color: '#ae2a19',
            borderRadius: 6, padding: '9px 12px', fontSize: 14, marginBottom: 12,
          }}>
            {error}
          </div>
        )}
        {wipExceeded && (
          <div style={{
            background: '#fff7d6', border: '1px solid #f5cd47', color: '#7f5f01',
            borderRadius: 6, padding: '9px 12px', fontSize: 14, marginBottom: 12,
          }}>
            WIP limit exceeded: {inProgressCount} issues in progress, the board allows {board.wip_limit}.
          </div>
        )}

        {issues === null && <p style={{ color: MUTED }}>Loading…</p>}

        {lanes.map((lane) => (
          <div key={lane.key} style={{ marginBottom: 18 }}>
            {lane.label && (
              <div style={{
                fontSize: 13, fontWeight: 700, color: MUTED, padding: '6px 2px',
                borderBottom: `1px solid ${BORDER}`, marginBottom: 8,
              }}>
                {lane.label} <span style={{ fontWeight: 500 }}>({lane.issues.length})</span>
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${ISSUE_STATES.length}, minmax(220px, 1fr))`, gap: 10, overflowX: 'auto' }}>
              {ISSUE_STATES.map((state) => {
                const columnIssues = lane.issues.filter((issue) => issue.state === state);
                const isWipColumn = state === 'in_progress' && Boolean(board?.wip_limit);
                // The limit belongs to the board, not to the swimlane, so the total is
                // reported once in the banner above. Here it only marks the columns that
                // actually hold work in progress — an empty lane is not the offender.
                const overLimit = isWipColumn && wipExceeded && columnIssues.length > 0;
                return (
                  <div
                    key={state}
                    onDragOver={(event) => { event.preventDefault(); setHover({ state, beforeId: null }); }}
                    onDrop={(event) => { event.preventDefault(); handleDrop(event, state, null); }}
                    style={{
                      background: hover?.state === state ? '#e9f2ff' : '#f1f2f4',
                      borderRadius: 6, minHeight: 120, paddingBottom: 8,
                      outline: overLimit ? '2px solid #f5cd47' : 'none',
                    }}
                  >
                    <div style={{ ...columnHeaderStyle, color: STATE_COLORS[state] }}>
                      <span>{STATE_LABELS[state]}</span>
                      <span style={{ color: MUTED, fontWeight: 600 }}>{columnIssues.length}</span>
                      {isWipColumn && (
                        <span style={{ marginLeft: 'auto', color: overLimit ? '#ae2a19' : MUTED, fontWeight: 600 }}>
                          max {board.wip_limit}
                        </span>
                      )}
                    </div>
                    {columnIssues.map((issue) => (
                      <IssueCard
                        key={issue.id}
                        issue={issue}
                        busy={busyId === issue.id}
                        draggable={canWrite}
                        isHovered={hover?.state === state && hover?.beforeId === issue.id}
                        onDragStart={(event) => {
                          event.dataTransfer.setData('text/plain', String(issue.id));
                          event.dataTransfer.effectAllowed = 'move';
                          setDragging(issue);
                        }}
                        onDragEnd={() => { setDragging(null); setHover(null); }}
                        onDragOver={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          setHover({ state, beforeId: issue.id });
                        }}
                        onDrop={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          handleDrop(event, state, issue);
                        }}
                      />
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {issues !== null && visibleIssues.length === 0 && (
          <p style={{ color: MUTED, fontSize: 14 }}>
            No issue matches the current filters.
          </p>
        )}
      </div>
    </div>
  );
}

function epicLabel(epics, epicId) {
  const epic = (epics ?? []).find((issue) => issue.id === epicId);
  return epic ? `${epic.id_presentation} ${epic.summary}` : 'Epic';
}

// Rank of the dragged card after the drop: halfway between its new neighbours,
// or last + 100 when it lands at the end of a column. Returns null when the
// position does not change.
function rankForDrop(allIssues, issue, toState, beforeIssue) {
  const column = allIssues
    .filter((candidate) => candidate.state === toState && candidate.id !== issue.id)
    .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  if (!beforeIssue) {
    const last = column[column.length - 1];
    return last ? Number(last.rank ?? 0) + 100 : 100;
  }
  const index = column.findIndex((candidate) => candidate.id === beforeIssue.id);
  if (index === -1) return null;
  const previous = index === 0 ? 0 : Number(column[index - 1].rank ?? 0);
  const next = Number(column[index].rank ?? 0);
  const rank = Math.floor((previous + next) / 2);
  // No integer left between the two neighbours: keep the card where it is
  // rather than silently landing somewhere else.
  return rank > previous && rank < next ? rank : null;
}

function IssueCard({ issue, busy, draggable, isHovered, ...handlers }) {
  const labels = issueLabels(issue);
  return (
    <div
      draggable={draggable && !busy}
      {...handlers}
      style={{
        background: SURFACE, borderRadius: 4, margin: '0 8px 8px', padding: '10px 10px 8px',
        boxShadow: '0 1px 1px rgba(9,30,66,0.25)', cursor: draggable ? 'grab' : 'default',
        opacity: busy ? 0.5 : 1,
        borderTop: isHovered ? `3px solid ${ACCENT}` : '3px solid transparent',
      }}
    >
      <a
        href={`#/admin/issue/${issue.id}`}
        onClick={(event) => event.stopPropagation()}
        style={{ textDecoration: 'none', color: INK, fontSize: 14, display: 'block', marginBottom: 8 }}
      >
        {issue.summary}
      </a>
      {labels.length > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
          {labels.map((label) => (
            <span key={label.id} style={{
              background: `${label.color}22`, color: label.color, border: `1px solid ${label.color}55`,
              borderRadius: 3, padding: '0 5px', fontSize: 10, fontWeight: 700,
            }}>{label.name}</span>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <TypeMark type={issue.type} />
        <span style={{ fontSize: 12, fontWeight: 700, color: MUTED }}>{issue.id_presentation}</span>
        <PriorityMark priority={issue.priority} />
        <span style={{ flex: 1 }} />
        {issue.story_points != null && (
          <span style={{
            background: '#ebecf0', color: MUTED, borderRadius: 10, padding: '1px 7px',
            fontSize: 11, fontWeight: 700,
          }}>{issue.story_points}</span>
        )}
        <Avatar member={issue.assignee} size={22} />
      </div>
    </div>
  );
}

export const inputStyle = {
  border: `1px solid ${BORDER}`, borderRadius: 4, padding: '6px 9px', fontSize: 13,
  background: SURFACE, color: INK, minWidth: 150,
};

export function Select({ value, onChange, options, placeholder }) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      style={{ ...inputStyle, cursor: 'pointer' }}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}
