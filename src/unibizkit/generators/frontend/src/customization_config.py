import json

from ..context import Context
from .resources.helpers import generate_field_components

_TEMPLATE = """// Presentation customization runtime.
//
// BASE is the evaluated presentation config baked at generation time; OVERLAYS
// are the model's presentation-custom-NN.jsonc files in ascending NN order.
// mergeCustomization applies the overlays that match the user's roles (empty
// roles = everyone; later files win) and returns the effective menu, list
// configuration, hidden form fields, labels and hidden workflow states.
// Role scoping is a presentation convenience, not security: every overlay
// ships in the bundle and data access is still enforced by the backend.

export const BASE = __BASE__;

export const OVERLAYS = __OVERLAYS__;

export const ROLES = __ROLES__;

// Where design mode is available ('off' | 'dev' | 'production'). Baked as a
// static constant so builds with 'off'/'dev' tree-shake the design tools away.
export const DESIGNER = __DESIGNER__;

const applies = (overlay, roles) =>
  !overlay.roles || overlay.roles.length === 0 || overlay.roles.some((role) => roles.includes(role));

// Tiny stable hash so a customized column set gets its own DatagridConfigurable
// preference bucket: the user's manual show/hide choices never fight an overlay
// change, and `omit` (initial-only per preference key) applies fresh.
const hashKey = (text) => {
  let hash = 5381;
  for (let i = 0; i < text.length; i++) hash = ((hash << 5) + hash + text.charCodeAt(i)) >>> 0;
  return hash.toString(36);
};

// --- Menu patch operations ---------------------------------------------------
// Overlays patch the menu with granular ops (rename/move/remove/add) instead of
// replacing it, so customizations keep working as the base menu evolves. A
// target is a concept/workflow name (leaf entries), a group label, or a
// '/'-separated label path; an unresolved target skips the op.

const skip = (op, reason) => {
  if (import.meta.env.DEV) console.warn(`[ubk] menu op skipped (${reason}):`, op);
};

const matchesTarget = (item, name) =>
  item.concept === name || item.workflow === name || item.label === name;

// Breadth-first (shallowest match wins); returns { parent: array, index } or null.
const findEntry = (items, target) => {
  const segments = target.split('/');
  if (segments.length > 1) {
    let scope = items;
    for (let i = 0; i < segments.length - 1; i++) {
      const group = scope.find((item) => item.children && matchesTarget(item, segments[i]));
      if (!group) return null;
      scope = group.children;
    }
    const index = scope.findIndex((item) => matchesTarget(item, segments[segments.length - 1]));
    return index === -1 ? null : { parent: scope, index };
  }
  const queue = [items];
  while (queue.length) {
    const scope = queue.shift();
    const index = scope.findIndex((item) => matchesTarget(item, target));
    if (index !== -1) return { parent: scope, index };
    scope.forEach((item) => { if (item.children) queue.push(item.children); });
  }
  return null;
};

// Destination children array for move/add: '' = top level, otherwise a group
// target; `fallback` covers the omitted case (move: current parent, add: root).
const destinationFor = (menu, op, fallback) => {
  if (op.into === undefined) return fallback;
  if (op.into === '') return menu;
  const found = findEntry(menu, op.into);
  const group = found && found.parent[found.index];
  return group && group.children ? group.children : null;
};

const insertAt = (destination, op, item) => {
  const position = op.position === undefined
    ? destination.length
    : Math.min(op.position, destination.length);
  destination.splice(position, 0, item);
};

const applyMenuOps = (menu, ops) => {
  for (const op of ops) {
    if (op.op === 'add') {
      if (!op.item) { skip(op, 'malformed op'); continue; }
      const destination = destinationFor(menu, op, menu);
      if (!destination) { skip(op, 'destination not found'); continue; }
      insertAt(destination, op, JSON.parse(JSON.stringify(op.item)));
      continue;
    }
    // Malformed entries (e.g. a stale draft or file from the old whole-menu
    // format still in local storage) must degrade to a no-op, never crash.
    if (!op || typeof op.target !== 'string') { skip(op, 'malformed op'); continue; }
    const found = findEntry(menu, op.target);
    if (!found) { skip(op, 'target not found'); continue; }
    if (op.op === 'rename') {
      found.parent[found.index].label = op.label;
    } else if (op.op === 'remove') {
      found.parent.splice(found.index, 1);
    } else if (op.op === 'move') {
      // Detach first so a destination inside the moved subtree can't resolve.
      const [item] = found.parent.splice(found.index, 1);
      const destination = destinationFor(menu, op, found.parent);
      if (!destination) {
        found.parent.splice(found.index, 0, item);
        skip(op, 'destination not found');
        continue;
      }
      insertAt(destination, op, item);
    }
  }
};

const applyHideShow = (target, concept, cfg) => {
  let hidden = target[concept];
  if (!hidden) {
    hidden = new Set();
    target[concept] = hidden;
  }
  (cfg.hide || []).forEach((name) => hidden.add(name));
  (cfg.show || []).forEach((name) => hidden.delete(name));
};

// Form width overrides: overlay fraction -> MUI grid columns (CGrid `sm`).
export const SIZE_COLS = { '1/4': 3, '1/3': 4, '1/2': 6, '2/3': 8, full: 12 };

// Reorders a form's entry-name array in place with the accumulated move
// patches. Like menu targets, an entry name that does not resolve is skipped —
// silently, because the same moves are also applied to lists with a different
// entry set (show views), where block names legitimately don't exist.
export const applyFormMoves = (order, moves) => {
  for (const move of moves) {
    const index = order.indexOf(move.field);
    if (index === -1) continue;
    order.splice(index, 1);
    order.splice(Math.min(move.position, order.length), 0, move.field);
  }
  return order;
};

export function mergeCustomization(overlays, roles) {
  const active = overlays.filter((overlay) => applies(overlay, roles));

  let menu = BASE.menu;
  if (menu) {
    menu = JSON.parse(JSON.stringify(menu));
    for (const overlay of active) {
      if (overlay.menu) applyMenuOps(menu, overlay.menu);
    }
  }

  const labels = { fields: {}, titles: {} };
  const hiddenFields = {};
  const hiddenStates = {};
  const listOverrides = {};
  const fieldSizes = {};
  const formMoves = {};
  for (const overlay of active) {
    if (overlay.labels) {
      Object.assign(labels.fields, overlay.labels.fields);
      Object.assign(labels.titles, overlay.labels.titles);
    }
    for (const [concept, cfg] of Object.entries(overlay.lists || {})) {
      listOverrides[concept] = { ...listOverrides[concept], ...cfg };
    }
    for (const [concept, cfg] of Object.entries(overlay.forms || {})) {
      applyHideShow(hiddenFields, concept, cfg);
      for (const [field, size] of Object.entries(cfg.sizes || {})) {
        fieldSizes[`${concept}.${field}`] = size;
      }
      if (cfg.move && cfg.move.length) {
        formMoves[concept] = (formMoves[concept] || []).concat(cfg.move);
      }
    }
    for (const [concept, cfg] of Object.entries(overlay.workflow_states || {})) {
      applyHideShow(hiddenStates, concept, cfg);
    }
  }

  const lists = {};
  for (const [concept, base] of Object.entries(BASE.lists)) {
    const override = listOverrides[concept] || {};
    const visible = (override.columns || base.columns).filter((name) => base.pool.includes(name));
    const sortText = override.sort || base.sort;
    const customized = !!override.columns && visible.join('|') !== base.columns.join('|');
    lists[concept] = {
      // Visible columns first (their order defines the view), then the rest of
      // the pool, hidden through `omit` but available in the column selector.
      order: visible.concat(base.pool.filter((name) => !visible.includes(name))),
      omit: base.pool.filter((name) => !visible.includes(name)),
      sort: sortText ? { field: sortText.split(' ')[0], order: sortText.split(' ')[1] } : null,
      prefKey: customized ? `${concept}.datagrid.c${hashKey(visible.join('|'))}` : `${concept}.datagrid`,
    };
  }

  return { menu, lists, labels, hiddenFields, hiddenStates, fieldSizes, formMoves };
}
"""


def generate(ctx: Context) -> str:
    lists = {}
    forms = {}
    for concept in ctx.concepts:
        # generate_field_components is the single source of truth for which list
        # columns exist and which are shown by default (evaluated list_field_rules
        # DSL); reusing it here keeps the runtime BASE from drifting.
        fields_res = generate_field_components(
            concept,
            ctx.concepts,
            ctx.concept_map,
            ctx.presentation_config,
            ctx.security_config,
        )
        lists[concept["name"]] = {
            "columns": fields_res["list_default_names"],
            "pool": fields_res["list_names"],
            "sort": ctx.presentation_config["list_sort"].get(concept["name"]),
        }
        # Form entry names (fields + composite blocks) in generated order; the
        # design-mode field editor uses them to compute move positions.
        forms[concept["name"]] = {
            "create": [name for name, _ in fields_res["create_form_entries"]],
            "edit": [name for name, _ in fields_res["edit_form_entries"]],
        }

    workflow_states = {
        name: [state["name"] for state in workflow["states"]]
        for name, workflow in ctx.workflow_config["_concept_workflow"].items()
    }
    base = {
        "menu": ctx.presentation_config.get("menu"),
        "lists": lists,
        "forms": forms,
        "workflowStates": workflow_states,
    }
    roles = [role["name"] for role in ctx.security_config.get("roles") or [{"name": "admin"}, {"name": "user"}]]

    return (
        _TEMPLATE
        .replace("__BASE__", json.dumps(base, indent=2))
        .replace("__OVERLAYS__", json.dumps(ctx.presentation_custom_config["overlays"], indent=2))
        .replace("__ROLES__", json.dumps(roles))
        .replace("__DESIGNER__", json.dumps(ctx.presentation_config["designer"]))
    )
