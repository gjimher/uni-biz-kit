_TEMPLATE = """import * as React from 'react';
import { useStore } from 'react-admin';
import { Grid } from '@mui/material';
import { DESIGNER, OVERLAYS__ROLES_IMPORT__, SIZE_COLS, applyFormMoves, mergeCustomization } from '../customizationConfig';
__SUPABASE_IMPORT__

const CustomizationContext = React.createContext(null);

// Production drafts belong to one authenticated browser session. Development
// keeps using react-admin's existing persistent store for model-file drafts.
const readSessionValue = (key, initialValue) => {
  try {
    const stored = window.sessionStorage.getItem(key);
    return stored === null ? initialValue : JSON.parse(stored);
  } catch {
    return initialValue;
  }
};

const useSessionValue = (key, initialValue) => {
  const [state, setState] = React.useState(() => ({ key, value: readSessionValue(key, initialValue) }));
  const value = state.key === key ? state.value : readSessionValue(key, initialValue);
  const valueRef = React.useRef(value);
  valueRef.current = value;
  React.useEffect(() => {
    if (state.key !== key) setState({ key, value: readSessionValue(key, initialValue) });
  }, [key, initialValue, state.key]);
  const setValue = React.useCallback((nextValue) => {
    const resolved = typeof nextValue === 'function' ? nextValue(valueRef.current) : nextValue;
    try {
      if (resolved === initialValue) window.sessionStorage.removeItem(key);
      else window.sessionStorage.setItem(key, JSON.stringify(resolved));
    } catch {
      // Keep the in-memory draft usable when sessionStorage is unavailable.
    }
    valueRef.current = resolved;
    setState({ key, value: resolved });
  }, [key, initialValue]);
  return [value, setValue];
};

// Where the design tools are available: 'production' always (per-user
// personalization), 'dev' only on the Vite dev server. Both terms are
// statically foldable, so builds with designer 'off'/'dev' remove the dynamic
// import()s and the whole devtools tree never enters the bundle.
const DESIGN_TOOLS_AVAILABLE = DESIGNER === 'production' || (DESIGNER === 'dev' && import.meta.env.DEV);
// Personal (per-user) designs live in the _design table and apply in builds;
// the dev server keeps editing the model's presentation-custom files instead.
export const PERSONAL_DESIGNER = DESIGNER === 'production' && !import.meta.env.DEV;

const LazyDesignTools = DESIGN_TOOLS_AVAILABLE
  ? React.lazy(() => import('../devtools/DesignTools'))
  : null;
const LazyDesignBadge = DESIGN_TOOLS_AVAILABLE
  ? React.lazy(() => import('../devtools/DesignBadge'))
  : null;

export const useCustomization = () => React.useContext(CustomizationContext);

export const DevDesignTools = () => {
  if (!LazyDesignTools) return null;
  return (
    <React.Suspense fallback={null}>
      <LazyDesignTools />
    </React.Suspense>
  );
};

// The "D" chip shown next to a designable element while design mode is active.
export const DesignBadge = ({ target }) => {
  const custom = useCustomization();
  if (!LazyDesignBadge || !custom || !custom.designMode) return null;
  return (
    <React.Suspense fallback={null}>
      <LazyDesignBadge target={target} />
    </React.Suspense>
  );
};

__SESSION_ROLES_HELPER__export const CustomizationProvider = ({ children }) => {
  const [devDraft, setDevDraft] = useStore('ubk.design.draft', null);
  const [devDesignEnabled, setDevDesignEnabled] = useStore('ubk.design.enabled', false);
  const [devOverlays, setDevOverlays] = React.useState(null);
__ROLES_STATE__
  const personalStorePrefix = `ubk.design.${userId || 'anonymous'}`;
  const [personalDraft, setPersonalDraft] = useSessionValue(`${personalStorePrefix}.draft`, null);
  const [personalDesignEnabled, setPersonalDesignEnabled] = useSessionValue(`${personalStorePrefix}.enabled`, false);
  const draft = PERSONAL_DESIGNER ? personalDraft : devDraft;
  const setDraft = PERSONAL_DESIGNER ? setPersonalDraft : setDevDraft;
  const designEnabled = PERSONAL_DESIGNER ? personalDesignEnabled : devDesignEnabled;
  const setDesignEnabled = PERSONAL_DESIGNER ? setPersonalDesignEnabled : setDevDesignEnabled;
  React.useEffect(() => {
    if (!import.meta.env.DEV) return;
    // In dev, prefer the live overlay files served by the Vite endpoint so a
    // save from the editor applies on reload without regenerating the app.
    fetch('/__ubk/presentation-custom')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data && data.overlays) setDevOverlays(data.overlays);
      })
      .catch(() => {});
  }, []);

  const designMode = !!(DESIGN_TOOLS_AVAILABLE && designEnabled && (!PERSONAL_DESIGNER || userId));
__PERSONAL_STATE__
  const value = React.useMemo(() => {
    let overlays = devOverlays || OVERLAYS;
    let roles = userRoles;
    let baseline = null;
    const personalDraft = !!(designMode && draft && draft.personal);
    if (designMode && draft && !personalDraft) {
      // The pending draft is just one more overlay, replacing the file it
      // targets at its position in the NN order — WYSIWYG by construction.
      const withoutDraft = overlays.filter(
        (overlay) => overlay.file !== (draft.sourceFile || draft.file)
      );
      // Preview the app as the roles the draft is aimed at.
      if (draft.roles && draft.roles.length) roles = draft.roles;
      // The state the saved file will land on (the chain without its target
      // file): editors compare against it to record only real deltas.
      baseline = mergeCustomization(withoutDraft, roles);
      overlays = withoutDraft
        .concat(draft)
        .sort((a, b) => (a.order || 0) - (b.order || 0));
    }
    // The personal design (or its pending draft) is the most specific layer:
    // it applies last, on top of every model overlay.
    const personal = personalDraft ? draft : personalDesign;
    if (personal) {
      if (personalDraft) baseline = mergeCustomization(overlays, roles);
      overlays = overlays.concat({ ...personal, file: '__personal__', roles: [] });
    }
    const merged = mergeCustomization(overlays, roles);
    return {
      ...merged,
      designMode,
      userRoles,
      draft,
      setDraft,
      designEnabled,
      setDesignEnabled,
      baselineHiddenFields: (baseline || merged).hiddenFields,
    };
  }, [
    devOverlays, draft, designMode, userRoles, personalDesign,
    setDraft, designEnabled, setDesignEnabled,
  ]);

  return <CustomizationContext.Provider value={value}>{children}</CustomizationContext.Provider>;
};

// Applies a label override to an element and, when it wraps a single child
// (ReferenceInput and friends resolve the label on the child), to that child.
const withLabel = (element, label) => {
  if (!label) return element;
  const child = element.props && element.props.children;
  if (React.isValidElement(child)) {
    return React.cloneElement(element, { label }, React.cloneElement(child, { label }));
  }
  return React.cloneElement(element, { label });
};

// Form-field cell: applies hide + label + width overrides and hosts the design
// badge. `entry` is the reorder unit the field belongs to (defaults to itself).
export const CGrid = ({ concept, field, entry, children, ...gridProps }) => {
  const custom = useCustomization();
  const hidden = custom && custom.hiddenFields[concept];
  if (hidden && hidden.has(field)) return null;
  const label = custom && custom.labels.fields[`${concept}.${field}`];
  const size = custom && SIZE_COLS[custom.fieldSizes[`${concept}.${field}`]];
  return (
    <Grid item {...gridProps} {...(size ? { sm: size } : {})} sx={{ position: 'relative' }}>
      {withLabel(children, label)}
      <DesignBadge target={{ kind: 'field', concept, field, entry: entry || field }} />
    </Grid>
  );
};

// Create/edit form entries (fields and composite blocks) in the customized
// order; hide/label/width overrides are applied inside each entry by CGrid.
export const renderFormEntries = (concept, entries, custom) => {
  let ordered = entries;
  const moves = custom && custom.formMoves[concept];
  if (moves && moves.length) {
    const order = applyFormMoves(entries.map(([name]) => name), moves);
    ordered = order.map((name) => entries.find(([entryName]) => entryName === name));
  }
  return ordered.map(([name, element]) => <React.Fragment key={name}>{element}</React.Fragment>);
};

// List columns in the customized order (Datagrid headers read the label prop
// of each direct child, so the override is applied on the column element).
export const renderColumns = (concept, columns, custom) =>
  custom.lists[concept].order
    .filter((name) => name in columns)
    .map((name) => {
      const label = custom.labels.fields[`${concept}.${name}`];
      return React.cloneElement(columns[name], label ? { key: name, label } : { key: name });
    });

// Show-view fields with hide + label overrides applied, following the form
// move patches where the entry names match (block names simply don't resolve).
export const renderShowFields = (concept, fields, custom) => {
  const hidden = custom.hiddenFields[concept];
  let ordered = fields;
  const moves = custom.formMoves[concept];
  if (moves && moves.length) {
    const order = applyFormMoves(fields.map(([name]) => name), moves);
    ordered = order.map((name) => fields.find(([fieldName]) => fieldName === name));
  }
  return ordered
    .filter(([name]) => !(hidden && hidden.has(name)))
    .map(([name, element]) => {
      const label = custom.labels.fields[`${concept}.${name}`];
      return React.cloneElement(element, label ? { key: name, label } : { key: name });
    });
};
"""


_SESSION_ROLES_HELPER = """// The user's roles come straight from the Supabase session (same claim the
// authProvider reads): available on first paint after a reload and updated on
// every auth state change, with no query-cache staleness in between.
const sessionRoles = (session) => {
  const candidate = session && session.user && session.user.app_metadata && session.user.app_metadata.roles;
  return Array.isArray(candidate) ? candidate.filter((role) => ROLES.includes(role)) : [];
};

"""

_PERSONAL_STATE = """  // Saved per-user personalization: fetched once the session user is known.
  // Saves and resets reload the page, which refetches it here.
  const [personalDesign, setPersonalDesign] = React.useState(null);
  React.useEffect(() => {
    if (!PERSONAL_DESIGNER) return undefined;
    let cancelled = false;
    const fetchDesign = (session) => {
      const user = session && session.user;
      if (!user) {
        if (!cancelled) setPersonalDesign(null);
        return;
      }
      supabaseClient
        .from('_design')
        .select('design')
        .eq('_security_owner_id', user.id)
        .limit(1)
        .then(({ data }) => {
          if (!cancelled) setPersonalDesign((data && data[0] && data[0].design) || null);
        });
    };
    supabaseClient.auth.getSession().then(({ data }) => fetchDesign(data && data.session));
    const { data: subscription } = supabaseClient.auth.onAuthStateChange((_event, session) => fetchDesign(session));
    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
    };
  }, []);
"""

_ROLES_STATE = """  const [userRoles, setUserRoles] = React.useState([]);
  const [userId, setUserId] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    const update = (session) => {
      if (cancelled) return;
      const next = sessionRoles(session);
      const nextUserId = session && session.user ? session.user.id : null;
      setUserRoles((previous) => (previous.join('|') === next.join('|') ? previous : next));
      setUserId(nextUserId);
      if (PERSONAL_DESIGNER) {
        const activeUser = window.sessionStorage.getItem('ubk.design.activeUser');
        if (activeUser && activeUser !== nextUserId) {
          window.sessionStorage.removeItem(`ubk.design.${activeUser}.draft`);
          window.sessionStorage.removeItem(`ubk.design.${activeUser}.enabled`);
        }
        if (nextUserId) window.sessionStorage.setItem('ubk.design.activeUser', nextUserId);
        else window.sessionStorage.removeItem('ubk.design.activeUser');
      }
    };
    supabaseClient.auth.getSession().then(({ data }) => update(data && data.session));
    const { data: subscription } = supabaseClient.auth.onAuthStateChange((_event, session) => update(session));
    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
    };
  }, []);
"""


def generate(has_auth_provider: bool) -> str:
    if has_auth_provider:
        roles_import = ", ROLES"
        supabase_import = "import { supabaseClient } from '../supabaseClient';\n"
        session_roles_helper = _SESSION_ROLES_HELPER
        roles_state = _ROLES_STATE
        personal_state = _PERSONAL_STATE
    else:
        # designer 'production' requires authentication (validated by the
        # loader), so without auth there is never a personal design to fetch.
        roles_import = ""
        supabase_import = ""
        session_roles_helper = ""
        roles_state = "  const userRoles = React.useMemo(() => [], []);\n  const userId = null;\n"
        personal_state = "  const personalDesign = null;\n"
    return (
        _TEMPLATE
        .replace("__ROLES_IMPORT__", roles_import)
        .replace("__SUPABASE_IMPORT__", supabase_import)
        .replace("__SESSION_ROLES_HELPER__", session_roles_helper)
        .replace("__ROLES_STATE__", roles_state)
        .replace("__PERSONAL_STATE__", personal_state)
    )
