import json

from ..context import Context
from .layout import profile_completion_dialog


def generate(ctx: Context, has_custom_layout: bool = False, has_auth_provider: bool = False) -> str:
    import_statements = []
    resource_components = []
    has_workflows = bool(ctx.workflow_config["_concept_workflow"])
    # 'workflow' is the path segment of the built-in task pages; the custom
    # router must prefix it with /admin like any resource route.
    admin_route_segments = [concept["name"] for concept in ctx.concepts]
    if has_workflows:
        admin_route_segments.append("workflow")
    admin_resource_names = json.dumps(admin_route_segments)

    for concept in ctx.concepts:
        resource_name = concept["name"]
        import_statements.append(
            f"import {{ {resource_name.upper()}_LIST, {resource_name.upper()}_CREATE, "
            f"{resource_name.upper()}_EDIT, {resource_name.upper()}_SHOW }} "
            f"from './resources/{resource_name}/{resource_name}.jsx';"
        )
        resource_components.append(
            f"""          {{(permissions?.['{resource_name}']?.includes('read') || permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('read') || permissions?.['*']?.includes('write')) ? (
              <Resource name="{resource_name}"
                  list={{ {resource_name.upper()}_LIST }}
                  create={{(permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write')) ? {resource_name.upper()}_CREATE : null}}
                  edit={{ {resource_name.upper()}_EDIT }}
                  show={{ {resource_name.upper()}_SHOW }}
              />
          ) : null}}"""
        )

    layout_import = ""
    layout_prop = ""
    if has_custom_layout:
        layout_import = "import { MyLayout } from './layout/MyLayout';"
        layout_prop = "\n            layout={MyLayout}"

    auth_import = ""
    login_prop = ""
    i18n_provider_def = ""
    i18n_prop = ""
    auth_routes_block = ""
    sso_redirect_import = ""
    sso_redirect_helpers = ""
    sso_redirect_element = ""
    ra_extra_imports = "AdminContext, AdminUI, Resource, localStorageStore"
    workflow_pages_import = ""
    workflow_routes_block = ""
    if has_workflows:
        ra_extra_imports += ", CustomRoutes"
        workflow_pages_import = (
            "import { WORKFLOW_ASSIGNABLE_TASKS, WORKFLOW_MY_TASKS } "
            "from './components/workflow_tasks';"
        )
        workflow_routes_block = """                <CustomRoutes>
                  <Route path="/workflow/assignable" element={<WORKFLOW_ASSIGNABLE_TASKS />} />
                  <Route path="/workflow/mine" element={<WORKFLOW_MY_TASKS />} />
                </CustomRoutes>"""
    profile_gate_element = ""
    if has_auth_provider:
        sso_enabled = ctx.security_config["sso"]["enabled"]
        login_prop_name = "MyLoginPage"
        auth_import = (
            "import { authProvider } from './authProvider';\n"
            "import { MyLoginPage } from './layout/MyLoginPage';\n"
            "import { MySetPasswordPage } from './layout/MySetPasswordPage';\n"
            "import { ForgotPasswordPage, defaultI18nProvider } from 'ra-supabase';"
        )
        if profile_completion_dialog.gates(ctx):
            auth_import += "\nimport { ProfileCompletionDialog } from './layout/ProfileCompletionDialog';"
            profile_gate_element = "\n          <ProfileCompletionDialog />"
        if sso_enabled:
            sso_redirect_import = "\nimport { supabaseClient } from './supabaseClient';"
            sso_redirect_helpers = """
const SSO_REDIRECT_PARAM = 'sso_redirect';
const POST_LOGIN_REDIRECT_KEY = 'unibizkit_post_login_redirect';

const rememberAdminRedirect = () => {
  if (window.location.hash.startsWith('#/admin')) {
    localStorage.setItem(POST_LOGIN_REDIRECT_KEY, window.location.hash);
  }
};

const consumeSsoRedirect = () => {
  const params = new URLSearchParams(window.location.search);
  const target = params.get(SSO_REDIRECT_PARAM);
  if (!target) return false;

  params.delete(SSO_REDIRECT_PARAM);
  const search = params.toString();
  window.history.replaceState(
    null,
    '',
    `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`
  );
  window.location.hash = target.startsWith('#/') ? target : `#${target.startsWith('/') ? target : `/${target}`}`;
  localStorage.removeItem(POST_LOGIN_REDIRECT_KEY);
  return true;
};

const SsoRedirectHandler = () => {
  React.useEffect(() => {
    let cancelled = false;
    rememberAdminRedirect();
    window.addEventListener('hashchange', rememberAdminRedirect);

    const maybeRedirect = async () => {
      if (!new URLSearchParams(window.location.search).has(SSO_REDIRECT_PARAM)) return;

      const { data } = await supabaseClient.auth.getSession();
      if (!cancelled && data.session) {
        consumeSsoRedirect();
      }
    };

    maybeRedirect();
    const { data: { subscription } } = supabaseClient.auth.onAuthStateChange((_event, session) => {
      if (session) {
        consumeSsoRedirect();
      }
    });

    return () => {
      cancelled = true;
      window.removeEventListener('hashchange', rememberAdminRedirect);
      subscription.unsubscribe();
    };
  }, []);

  return null;
};
"""
            sso_redirect_element = "\n    <SsoRedirectHandler />"
        login_prop = f"\n            loginPage={{{login_prop_name}}}"
        auth_routes_block = f"""        <Route path="/login" element={{<{login_prop_name} />}} />
        <Route path="/set-password" element={{<MySetPasswordPage />}} />
        <Route path="/forgot-password" element={{<ForgotPasswordPage />}} />
"""
        i18n_provider_def = "\nconst i18nProvider = defaultI18nProvider;"
        i18n_prop = "\n      i18nProvider={i18nProvider}"

    auth_prop = ""
    if has_auth_provider:
        auth_prop = "\n      authProvider={authProvider}"

    # Same per-app namespace as the Supabase auth storage (see supabase_client.py).
    store_prefix = ctx.deployment_config.get("base_uri", "/").strip("/") or "root"

    return f"""import * as React from 'react';
import {{ {ra_extra_imports} }} from 'react-admin';
import {{ reactRouterProvider }} from 'ra-core';
import {{
  HashRouter, Routes, Route,
  Link as RrLink,
  useMatch as rrUseMatch,
  useNavigate as rrUseNavigate,
}} from 'react-router-dom';
import {{ dataProvider }} from './dataProvider';
{layout_import}
{auth_import}
{sso_redirect_import}
import {{ PresentationRouter }} from './presentation/PresentationRouter';
{workflow_pages_import}
{chr(10).join(import_statements)}
{i18n_provider_def}
// Custom routerProvider so that React-Admin links and navigation prepend /admin
// when the path is absolute (e.g. /product → /admin/product).
// This is necessary because the outer HashRouter has no basename, while
// React-Admin expects to live at /admin/*.
const ADMIN_BASE = '/admin';
const AUTH_ROUTES = ['/login', '/forgot-password', '/set-password'];
const ADMIN_RESOURCE_NAMES = new Set({admin_resource_names});
const isAuthRoute = (to) =>
  AUTH_ROUTES.some(route => to === route || to.startsWith(`${{route}}?`) || to.startsWith(`${{route}}/`));
const isAdminRoute = (to) => to === ADMIN_BASE || to.startsWith(`${{ADMIN_BASE}}/`);
const firstPathSegment = (to) => to.split(/[/?#]/).filter(Boolean)[0] ?? '';
const isAdminResourceRoute = (to) => to === '/' || ADMIN_RESOURCE_NAMES.has(firstPathSegment(to));
const prefix = (to) =>
  typeof to === 'string' && to.startsWith('/') && !isAuthRoute(to) && !isAdminRoute(to) && isAdminResourceRoute(to) ? ADMIN_BASE + to : to;

const AdminLink = React.forwardRef(function AdminLink({{ to, ...rest }}, ref) {{
  return <RrLink to={{prefix(to)}} ref={{ref}} {{...rest}} />;
}});

function useAdminMatch(pattern) {{
  const opts = typeof pattern === 'string' ? {{ path: pattern }} : pattern;
  const prefixed = opts?.path?.startsWith('/') && !isAuthRoute(opts.path) && !isAdminRoute(opts.path) && isAdminResourceRoute(opts.path) ? ADMIN_BASE + opts.path : opts?.path;
  return rrUseMatch({{ ...opts, path: prefixed }});
}}

function useAdminNavigate() {{
  const navigate = rrUseNavigate();
  return React.useCallback(
    (to, opts) => navigate(prefix(to), opts),
    [navigate]
  );
}}

const adminRouterProvider = {{
  ...reactRouterProvider,
  Link: AdminLink,
  useMatch: useAdminMatch,
  useNavigate: useAdminNavigate,
  RouterWrapper: ({{ children }}) => <>{{children}}</>,
}};

// AdminContext defaults to an in-memory store; persist user preferences (like
// the Datagrid column selection) in localStorage instead, namespaced per app
// so models served from the same origin do not share them.
const store = localStorageStore(undefined, '{store_prefix}');
{sso_redirect_helpers}

const App = () => (
  <HashRouter>{sso_redirect_element}
    <AdminContext
      dataProvider={{dataProvider}}{auth_prop}{i18n_prop}
      basename="/admin"
      routerProvider={{adminRouterProvider}}
      store={{store}}
    >
      <Routes>
{auth_routes_block}
        <Route path="/admin/*" element={{<>{profile_gate_element}
          <AdminUI{layout_prop}{login_prop}>
            {{permissions => (
              <>
{chr(10).join(resource_components)}
{workflow_routes_block}
              </>
            )}}
          </AdminUI>
        </>}} />
        <Route path="/*" element={{<PresentationRouter hasAuthProvider={{{str(has_auth_provider).lower()}}} />}} />
      </Routes>
    </AdminContext>
  </HashRouter>
);

export default App;"""
