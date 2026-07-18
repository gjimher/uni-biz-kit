_TEMPLATE = """// Dev-only helpers for the design mode editor. The Vite dev server exposes
// /__ubk/presentation-custom (see vite.config.js) to list, read and write the
// model's presentation-custom-NN.jsonc overlay files.
const ENDPOINT = '/__ubk/presentation-custom';

// Relative $schema reference written into saved overlay files (IDE intellisense).
export const SCHEMA_REF = '__SCHEMA_REF__';

const SECTIONS = ['menu', 'lists', 'forms', 'labels', 'workflow_states'];

export const fetchCustomFiles = async () => {
  const response = await fetch(ENDPOINT);
  if (!response.ok) throw new Error(`Customization endpoint unavailable (${response.status})`);
  return response.json(); // { files: [...], overlays: [...] }
};

export const saveCustomFile = async (file, content, { previousFile = null, overwrite = false } = {}) => {
  const response = await fetch(ENDPOINT, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file, content, previousFile, overwrite }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Save failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
};

export const fileForOrder = (order) => `presentation-custom-${String(order).padStart(2, '0')}.jsonc`;

// The overlay sections of a draft, without the file/order/roles bookkeeping.
export const draftSections = (draft) => {
  const sections = {};
  for (const section of SECTIONS) {
    if (draft && draft[section] !== undefined) sections[section] = draft[section];
  }
  return sections;
};

export const draftToFileContent = (draft) => {
  const content = { $schema: SCHEMA_REF };
  if (draft.description) content.description = draft.description;
  content.roles = draft.roles || [];
  Object.assign(content, draftSections(draft));
  return JSON.stringify(content, null, 2) + '\\n';
};

// One entry per individual change, as { what, detail, remove }: readable text
// for the pending-changes list plus a mutator that deletes just that change
// from a draft copy (dropping sections that become empty, so saved files stay
// minimal). The chip badge counts these same entries.
export const summarizeDraft = (draft) => {
  const lines = [];
  if (!draft) return lines;
  const push = (what, detail, remove) => lines.push({ what, detail, remove });

  const cleanForms = (next, concept) => {
    const form = next.forms[concept];
    const empty = !(form.hide || []).length && !(form.show || []).length
      && !Object.keys(form.sizes || {}).length && !(form.move || []).length;
    if (empty) delete next.forms[concept];
    if (!Object.keys(next.forms).length) delete next.forms;
  };
  const cleanLabels = (next) => {
    if (!Object.keys(next.labels.fields || {}).length && !Object.keys(next.labels.titles || {}).length) {
      delete next.labels;
    }
  };

  (draft.menu || []).forEach((op, index) => {
    const removeOp = (next) => {
      next.menu.splice(index, 1);
      if (!next.menu.length) delete next.menu;
    };
    const position = op.position === undefined ? 'the end' : `position ${op.position}`;
    const destination = op.into === '' ? 'the top level' : op.into;
    if (op.op === 'rename') push(`menu · rename ${op.target}`, `"${op.label}"`, removeOp);
    else if (op.op === 'remove') push(`menu · remove ${op.target}`, '', removeOp);
    else if (op.op === 'move') {
      push(`menu · move ${op.target}`, destination ? `into ${destination}, ${position}` : `to ${position}`, removeOp);
    } else if (op.op === 'add') {
      const name = op.item && (op.item.concept || op.item.workflow || `group "${op.item.label}"`);
      push(`menu · add ${name}`, destination ? `into ${destination}` : 'at the top level', removeOp);
    } else {
      // E.g. a stale draft from an older format: inert at runtime, deletable here.
      push('menu · unrecognized change', '', removeOp);
    }
  });
  for (const [concept, cfg] of Object.entries(draft.lists || {})) {
    const parts = [];
    if (cfg.columns) parts.push(`columns: ${cfg.columns.join(', ')}`);
    if (cfg.sort) parts.push(`sort: ${cfg.sort}`);
    push(`${concept} list`, parts.join(' · '), (next) => {
      delete next.lists[concept];
      if (!Object.keys(next.lists).length) delete next.lists;
    });
  }
  for (const [concept, cfg] of Object.entries(draft.forms || {})) {
    for (const field of cfg.hide || []) {
      push(`${concept} form`, `hide ${field}`, (next) => {
        next.forms[concept].hide = next.forms[concept].hide.filter((name) => name !== field);
        cleanForms(next, concept);
      });
    }
    for (const field of cfg.show || []) {
      push(`${concept} form`, `show ${field}`, (next) => {
        next.forms[concept].show = next.forms[concept].show.filter((name) => name !== field);
        cleanForms(next, concept);
      });
    }
    for (const [field, size] of Object.entries(cfg.sizes || {})) {
      push(`${concept} form`, `${field} width ${size}`, (next) => {
        delete next.forms[concept].sizes[field];
        cleanForms(next, concept);
      });
    }
    (cfg.move || []).forEach((op, index) => {
      push(`${concept} form`, `move ${op.field} to ${op.position}`, (next) => {
        next.forms[concept].move.splice(index, 1);
        cleanForms(next, concept);
      });
    });
  }
  const labels = draft.labels || {};
  for (const [key, value] of Object.entries(labels.fields || {})) {
    push(`label ${key}`, `"${value}"`, (next) => {
      delete next.labels.fields[key];
      cleanLabels(next);
    });
  }
  for (const [key, value] of Object.entries(labels.titles || {})) {
    push(`title ${key}`, `"${value}"`, (next) => {
      delete next.labels.titles[key];
      cleanLabels(next);
    });
  }
  for (const [concept, cfg] of Object.entries(draft.workflow_states || {})) {
    push(
      `${concept} workflow`,
      cfg.hide && cfg.hide.length ? `hidden: ${cfg.hide.join(', ')}` : 'all states visible',
      (next) => {
        delete next.workflow_states[concept];
        if (!Object.keys(next.workflow_states).length) delete next.workflow_states;
      }
    );
  }
  return lines;
};

export const countChanges = (draft) => summarizeDraft(draft).length;
"""


def generate(schema_ref: str) -> str:
    return _TEMPLATE.replace("__SCHEMA_REF__", schema_ref.replace("\\", "/"))
