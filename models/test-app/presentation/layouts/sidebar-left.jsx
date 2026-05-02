import React from 'react';
import { Link } from 'react-router-dom';
import { model } from '../model';

export default function SidebarLeft({ frontmatter, children }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'sans-serif' }}>
      <nav style={{
        width: 220,
        borderRight: '1px solid #e0e0e0',
        padding: '16px 12px',
        background: '#fafafa',
        flexShrink: 0,
      }}>
        <Link to="/" style={{ display: 'block', marginBottom: 20, textDecoration: 'none' }}>
          <img src="/assets/logo.svg" alt={model.appName} style={{ width: 100 }} />
        </Link>

        {model.menu.map(group => (
          <div key={group.label} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#999', textTransform: 'uppercase', marginBottom: 4 }}>
              {group.label}
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {(group.children ?? []).map(item => (
                <li key={item.label} style={{ marginBottom: 2 }}>
                  {item.concept ? (
                    <a href={`#/admin/${item.concept}`} style={{ color: '#1976d2', textDecoration: 'none', fontSize: '0.9rem' }}>
                      {item.label}
                    </a>
                  ) : (
                    <span style={{ color: '#333', fontSize: '0.9rem' }}>{item.label}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}

        <div style={{ marginTop: 16, borderTop: '1px solid #e0e0e0', paddingTop: 12 }}>
          <a href="#/admin" style={{ color: '#555', fontSize: '0.9rem', textDecoration: 'none' }}>
            ⚙ Admin panel
          </a>
        </div>
      </nav>

      <main style={{ flex: 1, padding: 24, minWidth: 0 }}>
        {frontmatter?.title && (
          <h1 style={{ marginTop: 0, fontSize: '1.5rem' }}>{frontmatter.title}</h1>
        )}
        {children}
      </main>
    </div>
  );
}
