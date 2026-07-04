import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import MDEditor from '@uiw/react-md-editor';
import { supabaseClient } from '../../supabaseClient';
import { useSession, getProfile, signedUrl, signOut } from '../lib';

// ---------------------------------------------------------------------------
// Intranet portal home. The whole portal is private: this page redirects to
// /signin when there is no session. It greets the employee with their live
// balances (vacation days, flexibility hours), links the self-service pages
// under /priv, and shows the internal news feed (published articles) with an
// inline markdown reader — same reading experience as the cms-app example.
// HR/IT/admin users additionally get a link to the generated backoffice.
// ---------------------------------------------------------------------------

export const ACCENT = '#2563eb';
export const ACCENT_2 = '#0ea5e9';
export const INK = '#1e293b';
export const MUTED = '#64748b';
export const BORDER = '#e2e8f0';
export const BG_SOFT = '#f8fafc';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

// Workflow state → badge color, shared by the /priv pages.
export const STATE_COLORS = {
  draft: '#94a3b8', submitted: '#f59e0b', approved: '#10b981',
  open: '#f59e0b', in_progress: '#0ea5e9', resolved: '#10b981',
};

export default function PortalHome() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = useSession(); // undefined = loading, null = signed out
  const [me, setMe] = useState(null); // employee profile record (null while loading / no profile)
  const [openTickets, setOpenTickets] = useState(null);
  const [articles, setArticles] = useState(null);
  const [categories, setCategories] = useState([]);
  const [covers, setCovers] = useState({}); // article id -> signed cover URL

  // The intranet buckets are private (no anonymous access), so covers are
  // served through short-lived signed URLs instead of publicUrl.
  useEffect(() => {
    (articles ?? []).forEach((a) => {
      const path = coverPath(a);
      if (!path) return;
      signedUrl('article-documents', path)
        .then((url) => setCovers((prev) => (prev[a.id] ? prev : { ...prev, [a.id]: url })))
        .catch(() => {});
    });
  }, [articles]);

  useEffect(() => {
    if (session === null) navigate('/signin');
  }, [session, navigate]);

  useEffect(() => {
    if (!session) return;
    getProfile().then((profile) => setMe(profile?.record ?? null));
    supabaseClient
      .from('category')
      .select('id, name')
      .order('name')
      .then(({ data }) => setCategories(data ?? []));
    supabaseClient
      .from('article')
      .select('id, title, summary, body, category, published_date, is_featured, article_document(tag, storage_path)')
      .eq('status', 'published')
      .order('published_date', { ascending: false, nullsFirst: false })
      .then(({ data }) => setArticles(data ?? []));
  }, [session]);

  useEffect(() => {
    if (!me) return;
    supabaseClient
      .from('ticket')
      .select('id', { count: 'exact', head: true })
      .eq('requester', me.id)
      .neq('state', 'resolved')
      .then(({ count }) => setOpenTickets(count ?? 0));
  }, [me]);

  const categoryNames = useMemo(
    () => Object.fromEntries(categories.map((c) => [c.id, c.name])),
    [categories]
  );

  const readingId = searchParams.get('read');
  const reading = readingId ? (articles ?? []).find((a) => String(a.id) === readingId) : null;
  const openArticle = useCallback((id) => setSearchParams({ read: String(id) }), [setSearchParams]);

  if (!session) return null; // loading or about to redirect

  const vacationLeft = me ? (me.vacation_days_per_year ?? 0) - (me.vacation_days_used ?? 0) : null;
  const flexBalance = me ? (me.flex_hours_earned ?? 0) - (me.flex_hours_used ?? 0) : null;
  const featured = (articles ?? []).find((a) => a.is_featured) ?? (articles ?? [])[0];
  const rest = (articles ?? []).filter((a) => a !== featured);

  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: BG_SOFT }}>
      <PortalHeader session={session} active="home" />

      <main style={{ maxWidth: 1080, margin: '0 auto', padding: '0 20px 80px' }}>
        {reading ? (
          <Reader article={reading} img={covers[reading.id]} categoryName={categoryNames[reading.category]}
            onBack={() => setSearchParams({})} />
        ) : (
          <>
            <section style={{ marginTop: 30 }}>
              <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800 }}>
                {me ? `Hello, ${me.first_name} 👋` : 'Welcome 👋'}
              </h1>
              <p style={{ margin: '6px 0 0', color: MUTED, fontSize: 15 }}>
                {me?.job_title
                  ? `${me.job_title} — here is where your time, requests and company news live.`
                  : 'Your time, requests and company news, all in one place.'}
              </p>
            </section>

            <section style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16, marginTop: 22,
            }}>
              <StatTile emoji="🏖️" label="Vacation days left"
                value={vacationLeft == null ? '—' : vacationLeft}
                hint={me ? `${me.vacation_days_used ?? 0} of ${me.vacation_days_per_year} used` : 'No employee profile linked'}
                href="#/priv/requests" />
              <StatTile emoji="⏱️" label="Flexibility balance"
                value={flexBalance == null ? '—' : `${flexBalance >= 0 ? '+' : ''}${Number(flexBalance).toFixed(1)} h`}
                hint="Overtime you can spend as flex leave" href="#/priv/time" />
              <StatTile emoji="🎫" label="My open tickets"
                value={openTickets == null ? '—' : openTickets}
                hint="HR & IT helpdesk" href="#/priv/tickets" />
            </section>

            <section style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 12, marginTop: 18,
            }}>
              <QuickAction emoji="🔎" title="Find a colleague" subtitle="Directory & org chart" href="#/priv/directory" />
              <QuickAction emoji="🕘" title="Clock in / out" subtitle="Track today's hours" href="#/priv/time" />
              <QuickAction emoji="📅" title="Request time off" subtitle="Vacations & leaves" href="#/priv/requests" />
              <QuickAction emoji="🛟" title="Ask for help" subtitle="Open an HR or IT ticket" href="#/priv/tickets" />
            </section>

            <section style={{ marginTop: 40 }}>
              <h2 style={{ margin: '0 0 4px', fontSize: 21, fontWeight: 800 }}>Company news</h2>
              {articles === null ? (
                <Centered>Loading news…</Centered>
              ) : articles.length === 0 ? (
                <Centered>No published articles yet.</Centered>
              ) : (
                <>
                  {featured && (
                    <FeaturedCard article={featured} img={covers[featured.id]}
                      categoryName={categoryNames[featured.category]}
                      onOpen={() => openArticle(featured.id)} />
                  )}
                  <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                    gap: 20, marginTop: 20,
                  }}>
                    {rest.map((a) => (
                      <ArticleCard key={a.id} article={a} img={covers[a.id]}
                        categoryName={categoryNames[a.category]}
                        onOpen={() => openArticle(a.id)} />
                    ))}
                  </div>
                </>
              )}
            </section>
          </>
        )}
      </main>

      <footer style={{
        borderTop: `1px solid ${BORDER}`, padding: '18px 20px', textAlign: 'center',
        color: MUTED, fontSize: 13,
      }}>
        Intranet — generated by UniBizKit
      </footer>
    </div>
  );
}

// ===========================================================================
// Shared portal chrome (imported by the /priv pages)
// ===========================================================================

const NAV_ITEMS = [
  { key: 'home', label: 'Home', href: '#/' },
  { key: 'directory', label: 'Directory', href: '#/priv/directory' },
  { key: 'time', label: 'My Time', href: '#/priv/time' },
  { key: 'requests', label: 'Requests', href: '#/priv/requests' },
  { key: 'tickets', label: 'Tickets', href: '#/priv/tickets' },
];

export function PortalHeader({ session, active }) {
  const roles = session?.user?.app_metadata?.roles ?? [];
  const isStaff = roles.some((r) => ['admin', 'hr', 'it'].includes(r));
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20, background: 'rgba(255,255,255,0.94)',
      backdropFilter: 'blur(8px)', borderBottom: `1px solid ${BORDER}`,
    }}>
      <div style={{
        maxWidth: 1080, margin: '0 auto', padding: '12px 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap',
      }}>
        <a href="#/" style={{
          display: 'flex', alignItems: 'center', gap: 10, fontWeight: 800, fontSize: 19,
          color: INK, textDecoration: 'none',
        }}>
          <span style={{
            display: 'inline-flex', width: 32, height: 32, borderRadius: 9,
            background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`, color: '#fff',
            alignItems: 'center', justifyContent: 'center', fontSize: 18,
          }}>🏢</span>
          Intranet
        </a>
        <nav style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 14, flexWrap: 'wrap' }}>
          {NAV_ITEMS.map((item) => (
            <a key={item.key} href={item.href} style={{
              textDecoration: 'none', padding: '7px 12px', borderRadius: 8, fontWeight: 600,
              color: active === item.key ? ACCENT : INK,
              background: active === item.key ? '#eff6ff' : 'transparent',
            }}>{item.label}</a>
          ))}
          {isStaff && (
            <a href="#/admin" style={{
              textDecoration: 'none', padding: '7px 12px', borderRadius: 8, fontWeight: 700, color: ACCENT,
            }}>Backoffice</a>
          )}
          <span onClick={() => signOut()} style={{
            cursor: 'pointer', color: MUTED, padding: '7px 12px', fontWeight: 600,
          }}>Sign out</span>
        </nav>
      </div>
    </header>
  );
}

export function Badge({ label, color }) {
  return (
    <span style={{
      background: `${color}1a`, color, borderRadius: 999, padding: '3px 10px',
      fontSize: 12, fontWeight: 700, textTransform: 'capitalize', whiteSpace: 'nowrap',
    }}>{String(label).replace(/_/g, ' ')}</span>
  );
}

export function StateBadge({ state }) {
  return <Badge label={state} color={STATE_COLORS[state] ?? MUTED} />;
}

export function Card({ children, style }) {
  return (
    <div style={{
      background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 14,
      padding: '18px 20px', ...style,
    }}>{children}</div>
  );
}

export function Centered({ children }) {
  return (
    <div style={{ padding: '50px 0', textAlign: 'center', color: MUTED, fontSize: 15 }}>
      {children}
    </div>
  );
}

export function formatDay(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

// ===========================================================================
// Home building blocks
// ===========================================================================

function StatTile({ emoji, label, value, hint, href }) {
  return (
    <a href={href} style={{ textDecoration: 'none', color: INK }}>
      <Card style={{ height: '100%' }}>
        <div style={{ fontSize: 13, color: MUTED, fontWeight: 600 }}>{emoji} {label}</div>
        <div style={{ fontSize: 32, fontWeight: 800, margin: '6px 0 2px' }}>{value}</div>
        <div style={{ fontSize: 12.5, color: MUTED }}>{hint}</div>
      </Card>
    </a>
  );
}

function QuickAction({ emoji, title, subtitle, href }) {
  return (
    <a href={href} style={{ textDecoration: 'none', color: INK }}>
      <Card style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px' }}>
        <span style={{ fontSize: 24 }}>{emoji}</span>
        <span>
          <div style={{ fontWeight: 700, fontSize: 14.5 }}>{title}</div>
          <div style={{ color: MUTED, fontSize: 12.5 }}>{subtitle}</div>
        </span>
      </Card>
    </a>
  );
}

// ===========================================================================
// News cards + reader (cms-app style)
// ===========================================================================

function coverPath(article) {
  const docs = article.article_document ?? [];
  const byTag = (tag) => docs.find((d) => d.tag === tag);
  const cover = byTag('img_m') ?? byTag('img_l') ?? byTag('img_s');
  return cover?.storage_path ?? null;
}

function CategoryTag({ name }) {
  if (!name) return null;
  return (
    <span style={{
      display: 'inline-block', padding: '3px 10px', borderRadius: 999, fontSize: 12,
      fontWeight: 700, background: '#eff6ff', color: ACCENT, border: '1px solid #dbeafe',
    }}>{name}</span>
  );
}

function FeaturedCard({ article, img, categoryName, onOpen }) {
  return (
    <section onClick={onOpen} style={{
      marginTop: 16, borderRadius: 18, overflow: 'hidden', cursor: 'pointer',
      border: `1px solid ${BORDER}`, display: 'grid', background: '#fff',
      gridTemplateColumns: 'minmax(260px, 5fr) 7fr', minHeight: 240,
      boxShadow: '0 10px 30px rgba(15,23,42,0.06)',
    }}>
      <div style={{
        background: img ? `url(${img}) center/cover no-repeat` : `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`,
        minHeight: 200,
      }} />
      <div style={{ padding: '28px 32px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <CategoryTag name={categoryName} />
          <span style={{ color: MUTED, fontSize: 13 }}>{formatDay(article.published_date)}</span>
        </div>
        <h2 style={{ margin: '12px 0 8px', fontSize: 26, lineHeight: 1.2, fontWeight: 800 }}>
          {article.title}
        </h2>
        {article.summary && (
          <p style={{ margin: 0, color: MUTED, fontSize: 15, lineHeight: 1.6 }}>{article.summary}</p>
        )}
        <span style={{ marginTop: 14, color: ACCENT, fontWeight: 700, fontSize: 14.5 }}>
          Read the story →
        </span>
      </div>
    </section>
  );
}

function ArticleCard({ article, img, categoryName, onOpen }) {
  return (
    <article onClick={onOpen} style={{
      border: `1px solid ${BORDER}`, borderRadius: 14, overflow: 'hidden',
      cursor: 'pointer', background: '#fff', display: 'flex', flexDirection: 'column',
      transition: 'box-shadow .15s',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 12px 28px rgba(15,23,42,0.12)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
    >
      <div style={{
        aspectRatio: '16 / 9',
        background: img ? `url(${img}) center/cover no-repeat` : `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`,
      }} />
      <div style={{ padding: '14px 16px 18px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <CategoryTag name={categoryName} />
          <span style={{ color: MUTED, fontSize: 12 }}>{formatDay(article.published_date)}</span>
        </div>
        <h3 style={{ margin: '10px 0 6px', fontSize: 17.5, lineHeight: 1.3, fontWeight: 700 }}>
          {article.title}
        </h3>
        {article.summary && (
          <p style={{
            margin: 0, color: MUTED, fontSize: 13.5, lineHeight: 1.55,
            display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          }}>{article.summary}</p>
        )}
      </div>
    </article>
  );
}

function Reader({ article, img, categoryName, onBack }) {
  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <button onClick={onBack} style={{
        margin: '24px 0 0', padding: '8px 16px', borderRadius: 999, cursor: 'pointer',
        border: `1px solid ${BORDER}`, background: '#fff', color: INK, fontWeight: 600, fontSize: 14,
      }}>← All news</button>

      {img && (
        <div style={{
          marginTop: 22, borderRadius: 16, aspectRatio: '21 / 9',
          background: `url(${img}) center/cover no-repeat`,
        }} />
      )}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 26 }}>
        <CategoryTag name={categoryName} />
        <span style={{ color: MUTED, fontSize: 13 }}>{formatDay(article.published_date)}</span>
      </div>
      <h1 style={{ margin: '12px 0 6px', fontSize: 34, lineHeight: 1.15, fontWeight: 800 }}>
        {article.title}
      </h1>
      {article.summary && (
        <p style={{ margin: '6px 0 0', color: MUTED, fontSize: 17, lineHeight: 1.6 }}>{article.summary}</p>
      )}

      <div data-color-mode="light" style={{ marginTop: 28, background: '#fff', borderRadius: 14, padding: '20px 24px', border: `1px solid ${BORDER}` }}>
        <MDEditor.Markdown source={article.body ?? ''} style={{ fontSize: 16, lineHeight: 1.7 }} />
      </div>
    </div>
  );
}
