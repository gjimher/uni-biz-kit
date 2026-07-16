import json

from ...context import Context


def generate(ctx: Context) -> str:
    authenticated_page_patterns = json.dumps(ctx.presentation_config["authenticated_pages"], indent=2)
    return r"""import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { model } from './model';
import { useRequireSession, useProfileGateRedirect } from './lib';

const authenticatedPagePatterns = __AUTHENTICATED_PAGE_PATTERNS__;
const mdxPages = import.meta.glob('./pages/**/*.mdx', { eager: true });
const jsxPages = import.meta.glob('./pages/**/*.jsx', { eager: true });
const layoutModules = import.meta.glob('./layouts/**/*.jsx', { eager: true });

function getLayout(name) {
  const key = `./layouts/${name}.jsx`;
  return layoutModules[key]?.default ?? null;
}

function filePathToRoute(filePath, ext) {
  // filePath is like './pages/index.mdx' or './pages/sub/page.jsx'
  const route = filePath.slice('./pages'.length, -(ext.length + 1));
  if (route === '/index') return '/';
  return route || '/';
}

function normalizePagePath(path) {
  let normalized = path;
  if (normalized.startsWith('./')) normalized = normalized.slice(2);
  while (normalized.startsWith('/')) normalized = normalized.slice(1);
  return normalized;
}

function segmentMatches(patternSegment, pathSegment) {
  if (patternSegment === '*') return true;
  if (!patternSegment.includes('*')) return patternSegment === pathSegment;
  const escaped = patternSegment.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^${escaped.replace(/\*/g, '.*')}$`).test(pathSegment);
}

function globPartsMatch(patternParts, pathParts) {
  if (patternParts.length === 0) return pathParts.length === 0;

  const [patternHead, ...patternTail] = patternParts;
  if (patternHead === '**') {
    return globPartsMatch(patternTail, pathParts)
      || (pathParts.length > 0 && globPartsMatch(patternParts, pathParts.slice(1)));
  }

  return pathParts.length > 0
    && segmentMatches(patternHead, pathParts[0])
    && globPartsMatch(patternTail, pathParts.slice(1));
}

function pageRequiresAuth(filePath) {
  const pagePath = normalizePagePath(filePath);
  return authenticatedPagePatterns.some(pattern =>
    globPartsMatch(normalizePagePath(pattern).split('/'), pagePath.split('/'))
  );
}

const routeMap = (() => {
  const routes = {};
  for (const [path, mod] of Object.entries(mdxPages)) {
    const route = filePathToRoute(path, 'mdx');
    routes[route] = {
      Component: mod.default,
      frontmatter: mod.frontmatter ?? {},
      requiresAuth: pageRequiresAuth(path),
      isMdx: true,
    };
  }
  for (const [path, mod] of Object.entries(jsxPages)) {
    const route = filePathToRoute(path, 'jsx');
    routes[route] = { Component: mod.default, requiresAuth: pageRequiresAuth(path), isMdx: false };
  }
  return routes;
})();

// Replaces <a> in MDX: internal paths → Router <Link>, external/hash → plain <a>
function MdxLink({ href, children, ...props }) {
  if (href && !/^(https?:|mailto:|#|[/][/])/.test(href)) {
    return <Link to={href} {...props}>{children}</Link>;
  }
  return <a href={href} {...props}>{children}</a>;
}

function MdxPage({ Component, frontmatter }) {
  const Layout = frontmatter.layout ? getLayout(frontmatter.layout) : null;
  const components = { a: MdxLink };
  const content = <Component model={model} components={components} />;
  return Layout ? <Layout frontmatter={frontmatter}>{content}</Layout> : content;
}

// Guard for pages matching an authenticated_pages pattern: renders nothing
// until the session is known and bounces signed-out visitors to the app's own
// sign-in page, which returns them here after login. Built on the presentation
// lib so protected pages never depend on react-admin.
function RequireSession({ children }) {
  const session = useRequireSession(); // redirects to /signin when signed out
  if (!session) return null; // loading or redirecting
  return children;
}

function PresentationPage({ Component, frontmatter, isMdx, requiresAuth, hasAuthProvider }) {
  const content = isMdx
    ? <MdxPage Component={Component} frontmatter={frontmatter} />
    : <Component />;

  if (requiresAuth && hasAuthProvider) {
    return <RequireSession>{content}</RequireSession>;
  }

  return content;
}

// Mounts the global "ask_after_login" gate (see useProfileGateRedirect) for
// every session that lands on the custom UI, however it was established.
function ProfileGate() {
  useProfileGateRedirect();
  return null;
}

export function PresentationRouter({ hasAuthProvider = false }) {
  return (
    <>
    {hasAuthProvider && <ProfileGate />}
    <Routes>
      {Object.entries(routeMap).map(([path, { Component, frontmatter, requiresAuth, isMdx }]) => (
        <Route
          key={path}
          path={path}
          element={
            <PresentationPage
              Component={Component}
              frontmatter={frontmatter}
              isMdx={isMdx}
              requiresAuth={requiresAuth}
              hasAuthProvider={hasAuthProvider}
            />
          }
        />
      ))}
    </Routes>
    </>
  );
}
""".replace("__AUTHENTICATED_PAGE_PATTERNS__", authenticated_page_patterns)
