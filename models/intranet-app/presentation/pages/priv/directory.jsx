import React, { useEffect, useMemo, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { useSession, signedUrl } from '../../lib';
import {
  PortalHeader, Card, Centered, ACCENT, ACCENT_2, INK, MUTED, BORDER, BG_SOFT, FONT,
} from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/directory — employee search and org chart. Everyone can read the
// employee table (directory is company-wide), photos come from the public
// employee-documents bucket, and the org chart is built client-side from the
// manager self-relation.
// ---------------------------------------------------------------------------

export default function Directory() {
  const session = useSession();
  const [employees, setEmployees] = useState(null); // null = loading
  const [centers, setCenters] = useState([]);
  const [photos, setPhotos] = useState({}); // employee id -> signed photo URL
  const [query, setQuery] = useState('');
  const [centerFilter, setCenterFilter] = useState(null);
  const [tab, setTab] = useState('people'); // 'people' | 'org'

  // Private bucket: portraits are fetched through short-lived signed URLs.
  useEffect(() => {
    (employees ?? []).forEach((e) => {
      const photo = (e.employee_document ?? []).find((d) => d.tag === 'photo');
      if (!photo) return;
      signedUrl('employee-documents', photo.storage_path)
        .then((url) => setPhotos((prev) => (prev[e.id] ? prev : { ...prev, [e.id]: url })))
        .catch(() => {});
    });
  }, [employees]);

  useEffect(() => {
    supabaseClient
      .from('employee')
      .select('id, first_name, last_name, email, job_title, phone, manager, work_center, is_active, employee_document(tag, storage_path)')
      .eq('is_active', true)
      .order('first_name')
      .then(({ data }) => setEmployees(data ?? []));
    supabaseClient
      .from('work_center')
      .select('id, name, city')
      .order('name')
      .then(({ data }) => setCenters(data ?? []));
  }, []);

  const centerNames = useMemo(
    () => Object.fromEntries(centers.map((c) => [c.id, c.name])),
    [centers]
  );

  const filtered = useMemo(() => {
    if (!employees) return [];
    const q = query.trim().toLowerCase();
    return employees.filter((e) => {
      if (centerFilter != null && e.work_center !== centerFilter) return false;
      if (!q) return true;
      const haystack = `${e.first_name} ${e.last_name} ${e.job_title ?? ''} ${e.email ?? ''} ${centerNames[e.work_center] ?? ''}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [employees, query, centerFilter, centerNames]);

  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <PortalHeader session={session} active="directory" />

      <main style={{ maxWidth: 1080, margin: '0 auto', padding: '28px 20px 80px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>People</h1>
          <div style={{ display: 'flex', gap: 8 }}>
            <TabButton label="Directory" active={tab === 'people'} onClick={() => setTab('people')} />
            <TabButton label="Org chart" active={tab === 'org'} onClick={() => setTab('org')} />
          </div>
        </div>

        {tab === 'people' && (
          <>
            <div style={{ display: 'flex', gap: 10, marginTop: 18, flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by name, role, email or center…"
                style={{
                  flex: '1 1 260px', padding: '11px 14px', borderRadius: 10,
                  border: `1px solid ${BORDER}`, fontSize: 14, fontFamily: FONT, color: INK,
                }}
              />
              <Chip label="All centers" active={centerFilter == null} onClick={() => setCenterFilter(null)} />
              {centers.map((c) => (
                <Chip key={c.id} label={c.name} active={centerFilter === c.id} onClick={() => setCenterFilter(c.id)} />
              ))}
            </div>

            {employees === null ? (
              <Centered>Loading directory…</Centered>
            ) : filtered.length === 0 ? (
              <Centered>No employees match your search.</Centered>
            ) : (
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
                gap: 16, marginTop: 20,
              }}>
                {filtered.map((e) => (
                  <PersonCard key={e.id} employee={e} img={photos[e.id]} centerName={centerNames[e.work_center]} />
                ))}
              </div>
            )}
          </>
        )}

        {tab === 'org' && (
          employees === null ? (
            <Centered>Loading org chart…</Centered>
          ) : (
            <OrgChart employees={employees} photos={photos} centerNames={centerNames} />
          )
        )}
      </main>
    </div>
  );
}

// ===========================================================================
// People cards
// ===========================================================================

function Avatar({ employee, img, size = 52 }) {
  const initials = `${employee.first_name?.[0] ?? ''}${employee.last_name?.[0] ?? ''}`.toUpperCase();
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      background: img ? `url(${img}) center/cover no-repeat` : `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`,
      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontWeight: 800, fontSize: size * 0.36,
    }}>
      {img ? '' : initials}
    </div>
  );
}

function PersonCard({ employee, img, centerName }) {
  return (
    <Card style={{ display: 'flex', gap: 14, alignItems: 'flex-start', padding: '16px 18px' }}>
      <Avatar employee={employee} img={img} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 15.5 }}>
          {employee.first_name} {employee.last_name}
        </div>
        {employee.job_title && (
          <div style={{ color: MUTED, fontSize: 13, marginTop: 2 }}>{employee.job_title}</div>
        )}
        {centerName && (
          <div style={{
            display: 'inline-block', marginTop: 8, padding: '2px 9px', borderRadius: 999,
            background: '#eff6ff', color: ACCENT, fontSize: 11.5, fontWeight: 700,
          }}>{centerName}</div>
        )}
        <div style={{ marginTop: 8, fontSize: 12.5, color: MUTED, overflowWrap: 'anywhere' }}>
          {employee.email && <div>✉️ <a href={`mailto:${employee.email}`} style={{ color: ACCENT, textDecoration: 'none' }}>{employee.email}</a></div>}
          {employee.phone && <div>📞 {employee.phone}</div>}
        </div>
      </div>
    </Card>
  );
}

// ===========================================================================
// Org chart — nested cards built from the manager self-relation
// ===========================================================================

function OrgChart({ employees, photos, centerNames }) {
  const byManager = useMemo(() => {
    const map = {};
    for (const e of employees) {
      const key = e.manager ?? 'root';
      (map[key] ??= []).push(e);
    }
    return map;
  }, [employees]);

  const roots = byManager.root ?? [];
  if (roots.length === 0) {
    return <Centered>No employees without a manager — the org chart needs at least one root.</Centered>;
  }

  return (
    <div style={{ marginTop: 20 }}>
      {roots.map((e) => (
        <OrgNode key={e.id} employee={e} byManager={byManager} photos={photos} centerNames={centerNames} depth={0} />
      ))}
    </div>
  );
}

function OrgNode({ employee, byManager, photos, centerNames, depth }) {
  const reports = byManager[employee.id] ?? [];
  return (
    <div style={{ marginLeft: depth === 0 ? 0 : 34, position: 'relative', marginTop: 10 }}>
      {depth > 0 && (
        <div style={{
          position: 'absolute', left: -20, top: -10, bottom: reports.length ? 0 : 'auto',
          height: reports.length ? undefined : 38,
          borderLeft: `2px solid ${BORDER}`,
        }} />
      )}
      {depth > 0 && (
        <div style={{ position: 'absolute', left: -20, top: 28, width: 16, borderTop: `2px solid ${BORDER}` }} />
      )}
      <Card style={{ display: 'inline-flex', gap: 12, alignItems: 'center', padding: '10px 16px 10px 12px' }}>
        <Avatar employee={employee} img={photos[employee.id]} size={40} />
        <span>
          <span style={{ fontWeight: 700, fontSize: 14.5 }}>
            {employee.first_name} {employee.last_name}
          </span>
          <span style={{ color: MUTED, fontSize: 12.5, display: 'block' }}>
            {[employee.job_title, centerNames[employee.work_center]].filter(Boolean).join(' · ')}
          </span>
        </span>
      </Card>
      {reports.map((r) => (
        <OrgNode key={r.id} employee={r} byManager={byManager} photos={photos} centerNames={centerNames} depth={depth + 1} />
      ))}
    </div>
  );
}

// ===========================================================================
// Small helpers
// ===========================================================================

function TabButton({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 14, fontWeight: 600,
      border: `1px solid ${active ? ACCENT : BORDER}`,
      background: active ? ACCENT : '#fff', color: active ? '#fff' : INK,
    }}>{label}</button>
  );
}

function Chip({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '8px 14px', borderRadius: 999, cursor: 'pointer', fontSize: 13, fontWeight: 600,
      border: `1px solid ${active ? ACCENT : BORDER}`,
      background: active ? '#eff6ff' : '#fff', color: active ? ACCENT : INK,
    }}>{label}</button>
  );
}
