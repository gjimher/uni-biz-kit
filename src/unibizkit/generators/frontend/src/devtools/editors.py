_TEMPLATE = """import * as React from 'react';
import {
  Box, Button, Checkbox, FormControl, FormControlLabel, IconButton, InputLabel,
  MenuItem, Select, Switch, TextField, Tooltip, Typography,
} from '@mui/material';
import {
  ArrowDownward as ArrowDownwardIcon,
  ArrowUpward as ArrowUpwardIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import { useCustomization } from '../components/customization';
import { BASE, applyFormMoves } from '../customizationConfig';
import { model } from '../presentation/model';
import { EditorDialog } from './ui';

// Every editor mutates the pending draft exposed by the customization provider;
// the change is applied immediately through the same overlay merge the roles
// will see — WYSIWYG.
export const useUpdateDraft = () => {
  const { draft, setDraft } = useCustomization();
  return (mutator) => {
    const next = JSON.parse(JSON.stringify(draft || {}));
    mutator(next);
    setDraft(next);
  };
};

const moveItem = (items, index, delta) => {
  const target = index + delta;
  if (target < 0 || target >= items.length) return items;
  const next = items.slice();
  next[index] = items[target];
  next[target] = items[index];
  return next;
};

// --- Form field: visibility, label, width and position ------------------------

const FIELD_WIDTHS = ['1/4', '1/3', '1/2', '2/3', 'full'];

export const FieldEditor = ({ concept, field, entry, onClose }) => {
  const custom = useCustomization();
  const updateDraft = useUpdateDraft();
  const hidden = custom.hiddenFields[concept];
  const [visible, setVisible] = React.useState(!(hidden && hidden.has(field)));
  const [label, setLabel] = React.useState(custom.labels.fields[`${concept}.${field}`] || '');
  const [size, setSize] = React.useState(custom.fieldSizes[`${concept}.${field}`] || '');

  // The reorder unit: the field itself, or the composite block it belongs to.
  // Positions are computed on the edit form's effective entry order; create
  // and show views follow the same move patches.
  const entryName = entry || field;
  const entryOrder = applyFormMoves(
    (BASE.forms[concept] ? BASE.forms[concept].edit : []).slice(),
    custom.formMoves[concept] || []
  );
  const entryIndex = entryOrder.indexOf(entryName);

  const move = (delta) => {
    const position = entryIndex + delta;
    if (entryIndex === -1 || position < 0 || position >= entryOrder.length) return;
    updateDraft((draft) => {
      if (!draft.forms) draft.forms = {};
      if (!draft.forms[concept]) draft.forms[concept] = { hide: [], show: [] };
      const forms = draft.forms[concept];
      if (!forms.move) forms.move = [];
      const last = forms.move[forms.move.length - 1];
      // Compact bursts of arrow presses: each move states an absolute position.
      const op = { field: entryName, position };
      if (last && last.field === entryName) forms.move[forms.move.length - 1] = op;
      else forms.move.push(op);
    });
  };

  const apply = () => {
    // Only real deltas are recorded: a hide/show entry is written when the
    // desired visibility differs from the baseline (the overlay chain without
    // this draft), so "visible field left visible" adds no change.
    const baseline = custom.baselineHiddenFields[concept];
    const baselineHidden = !!(baseline && baseline.has(field));
    updateDraft((draft) => {
      if (!draft.forms) draft.forms = {};
      if (!draft.forms[concept]) draft.forms[concept] = { hide: [], show: [] };
      const forms = draft.forms[concept];
      forms.hide = (forms.hide || []).filter((name) => name !== field);
      forms.show = (forms.show || []).filter((name) => name !== field);
      if (visible && baselineHidden) forms.show.push(field);
      if (!visible && !baselineHidden) forms.hide.push(field);
      if (!forms.sizes) forms.sizes = {};
      if (size) forms.sizes[field] = size;
      else delete forms.sizes[field];
      if (!draft.labels) draft.labels = {};
      if (!draft.labels.fields) draft.labels.fields = {};
      if (label.trim()) draft.labels.fields[`${concept}.${field}`] = label.trim();
      else delete draft.labels.fields[`${concept}.${field}`];
      // Drop empty leftovers so a no-op apply records nothing at all.
      if (!forms.hide.length && !forms.show.length && !Object.keys(forms.sizes).length
          && !(forms.move || []).length) {
        delete draft.forms[concept];
      }
      if (!Object.keys(draft.forms).length) delete draft.forms;
      if (!Object.keys(draft.labels.fields).length && !Object.keys(draft.labels.titles || {}).length) {
        delete draft.labels;
      }
    });
    onClose();
  };

  return (
    <EditorDialog
      title="Customize field"
      subtitle={`${concept}.${field}`}
      onClose={onClose}
      onApply={apply}
      extraActions={(
        <>
          <Tooltip title={entryName === field ? 'Move earlier in the form' : `Move the ${entryName} block earlier`}>
            <IconButton size="small" onClick={() => move(-1)}><ArrowUpwardIcon fontSize="inherit" /></IconButton>
          </Tooltip>
          <Tooltip title={entryName === field ? 'Move later in the form' : `Move the ${entryName} block later`}>
            <IconButton size="small" onClick={() => move(1)}><ArrowDownwardIcon fontSize="inherit" /></IconButton>
          </Tooltip>
        </>
      )}
    >
      <FormControlLabel
        control={<Switch checked={visible} onChange={(event) => setVisible(event.target.checked)} />}
        label="Visible in forms"
      />
      <TextField
        label="Label override"
        value={label}
        onChange={(event) => setLabel(event.target.value)}
        fullWidth
        size="small"
        margin="dense"
        helperText="Empty = default label"
      />
      <FormControl size="small" fullWidth margin="dense">
        <InputLabel>Width</InputLabel>
        <Select label="Width" value={size} onChange={(event) => setSize(event.target.value)}>
          <MenuItem value="">(default)</MenuItem>
          {FIELD_WIDTHS.map((width) => (
            <MenuItem key={width} value={width}>{width}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        {entryName === field
          ? 'Position arrows apply immediately — the form updates behind this dialog.'
          : `This field is part of the "${entryName}" block: the arrows move the whole block.`}
      </Typography>
    </EditorDialog>
  );
};

// --- List: column visibility, order and default sort -------------------------

export const ListEditor = ({ concept, onClose }) => {
  const custom = useCustomization();
  const updateDraft = useUpdateDraft();
  const base = BASE.lists[concept];
  const cfg = custom.lists[concept];
  const omit = new Set(cfg.omit);
  const [columns, setColumns] = React.useState(
    cfg.order.map((name) => ({ name, visible: !omit.has(name) }))
  );
  const [sortField, setSortField] = React.useState(cfg.sort ? cfg.sort.field : '');
  const [sortOrder, setSortOrder] = React.useState(cfg.sort ? cfg.sort.order : 'ASC');

  const toggle = (index) => setColumns((cols) =>
    cols.map((col, i) => (i === index ? { ...col, visible: !col.visible } : col)));

  const apply = () => {
    updateDraft((draft) => {
      if (!draft.lists) draft.lists = {};
      const entry = { columns: columns.filter((col) => col.visible).map((col) => col.name) };
      if (sortField) entry.sort = `${sortField} ${sortOrder}`;
      draft.lists[concept] = entry;
    });
    onClose();
  };

  return (
    <EditorDialog title="Customize list" subtitle={`${concept} columns and sort`} onClose={onClose} onApply={apply}>
      <Typography variant="subtitle2" gutterBottom>Columns (checked = visible, in order)</Typography>
      {columns.map((col, index) => (
        <Box
          key={col.name}
          sx={{
            display: 'flex', alignItems: 'center', gap: 0.5, px: 0.5,
            borderRadius: 1, '&:hover': { bgcolor: 'action.hover' },
          }}
        >
          <Checkbox size="small" checked={col.visible} onChange={() => toggle(index)} />
          <Typography
            variant="body2"
            sx={{ flexGrow: 1, color: col.visible ? 'text.primary' : 'text.disabled' }}
          >
            {col.name}
          </Typography>
          <IconButton size="small" onClick={() => setColumns((cols) => moveItem(cols, index, -1))}>
            <ArrowUpwardIcon fontSize="inherit" />
          </IconButton>
          <IconButton size="small" onClick={() => setColumns((cols) => moveItem(cols, index, 1))}>
            <ArrowDownwardIcon fontSize="inherit" />
          </IconButton>
        </Box>
      ))}
      <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>Default sort</InputLabel>
          <Select label="Default sort" value={sortField} onChange={(event) => setSortField(event.target.value)}>
            <MenuItem value="">(default)</MenuItem>
            {['id'].concat(base.pool).map((name) => (
              <MenuItem key={name} value={name}>{name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 100 }}>
          <InputLabel>Direction</InputLabel>
          <Select label="Direction" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
            <MenuItem value="ASC">ASC</MenuItem>
            <MenuItem value="DESC">DESC</MenuItem>
          </Select>
        </FormControl>
      </Box>
    </EditorDialog>
  );
};

// --- Menu: per-item editors opened from the sidebar badges -------------------

const WORKFLOW_PAGES = ['assignable_tasks', 'my_tasks'];

// Menu edits append granular patch ops ({op: rename|move|remove|add, ...}) to
// the draft's `menu` — never a full menu copy — so saved files keep working as
// the base menu evolves. Bursts of edits on the same target (arrow presses,
// retyping a label) compact into one op: each op states an absolute outcome,
// so replacing the last one is equivalent to appending.
const useMenuOps = () => {
  const updateDraft = useUpdateDraft();
  return (op) => updateDraft((draft) => {
    if (!draft.menu) draft.menu = [];
    const last = draft.menu[draft.menu.length - 1];
    if (last && last.op === op.op && last.target === op.target && op.op !== 'add') {
      draft.menu[draft.menu.length - 1] = op;
    } else {
      draft.menu.push(op);
    }
  });
};

const itemsAt = (menu, path) => path.reduce((items, index) => items[index].children, menu);

// Patch-op address of the entry at `path`: concept/workflow name for leaves
// (stable across renames), '/'-joined label path for groups.
const targetFor = (menu, path) => {
  const labels = [];
  let items = menu;
  let item = null;
  for (const index of path) {
    item = items[index];
    labels.push(item.label);
    items = item.children || [];
  }
  if (item.concept) return item.concept;
  if (item.workflow) return item.workflow;
  return labels.join('/');
};

export const MenuItemEditor = ({ path, onClose }) => {
  const custom = useCustomization();
  const appendOp = useMenuOps();
  // Moving the item changes its index, so the path is kept as state.
  const [itemPath, setItemPath] = React.useState(path);
  const parentPath = itemPath.slice(0, -1);
  const index = itemPath[itemPath.length - 1];
  const siblings = itemsAt(custom.menu || [], parentPath);
  const item = siblings[index];
  const [label, setLabel] = React.useState(item ? item.label : '');
  if (!item) return null;

  const kind = item.concept ? `→ ${item.concept}` : item.workflow ? `→ ${item.workflow}` : 'group';
  const target = targetFor(custom.menu || [], itemPath);

  const move = (delta) => {
    const targetIndex = index + delta;
    if (targetIndex < 0 || targetIndex >= siblings.length) return;
    appendOp({ op: 'move', target, position: targetIndex });
    setItemPath(parentPath.concat(targetIndex));
  };

  const remove = () => {
    appendOp({ op: 'remove', target });
    onClose();
  };

  const apply = () => {
    if (label !== item.label) appendOp({ op: 'rename', target, label });
    onClose();
  };

  return (
    <EditorDialog
      title="Customize menu entry"
      subtitle={kind}
      onClose={onClose}
      onApply={apply}
      extraActions={(
        <>
          <Tooltip title="Move up">
            <IconButton size="small" onClick={() => move(-1)}><ArrowUpwardIcon fontSize="inherit" /></IconButton>
          </Tooltip>
          <Tooltip title="Move down">
            <IconButton size="small" onClick={() => move(1)}><ArrowDownwardIcon fontSize="inherit" /></IconButton>
          </Tooltip>
          <Button color="error" size="small" startIcon={<DeleteIcon />} onClick={remove}>
            Remove
          </Button>
        </>
      )}
    >
      <TextField
        label="Label"
        value={label}
        onChange={(event) => setLabel(event.target.value)}
        fullWidth
        size="small"
        margin="dense"
        autoFocus
      />
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        Moves and removal apply immediately — the menu updates behind this dialog.
      </Typography>
    </EditorDialog>
  );
};

export const AddMenuEntryDialog = ({ path, onClose }) => {
  const custom = useCustomization();
  const appendOp = useMenuOps();
  const [value, setValue] = React.useState('');
  const options = [{ id: 'group:', label: 'New group' }]
    .concat(model.concepts.map((concept) => ({ id: `concept:${concept.name}`, label: `Concept: ${concept.name}` })))
    .concat(WORKFLOW_PAGES.map((page) => ({ id: `workflow:${page}`, label: `Workflow: ${page.replaceAll('_', ' ')}` })));

  const apply = () => {
    if (!value) return;
    const [kind, name] = value.split(':');
    const item = kind === 'group' ? { label: 'New group', children: [] }
      : kind === 'concept' ? { label: name, concept: name }
        : { label: name.replaceAll('_', ' '), workflow: name };
    const op = { op: 'add', item };
    if (path.length) op.into = targetFor(custom.menu || [], path);
    appendOp(op);
    onClose();
  };

  return (
    <EditorDialog
      title="Add menu entry"
      subtitle={path.length ? 'into this group' : 'at top level'}
      onClose={onClose}
      onApply={apply}
      applyLabel="Add"
    >
      <FormControl size="small" fullWidth sx={{ mt: 1 }}>
        <InputLabel>Entry</InputLabel>
        <Select label="Entry" value={value} onChange={(event) => setValue(event.target.value)}>
          {options.map((option) => (
            <MenuItem key={option.id} value={option.id}>{option.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
    </EditorDialog>
  );
};

// --- Workflow: per-role state visibility -------------------------------------

export const WorkflowEditor = ({ concept, onClose }) => {
  const custom = useCustomization();
  const updateDraft = useUpdateDraft();
  const allStates = BASE.workflowStates[concept] || [];
  const hidden = custom.hiddenStates[concept];
  const [visible, setVisible] = React.useState(() => {
    const map = {};
    allStates.forEach((state) => { map[state] = !(hidden && hidden.has(state)); });
    return map;
  });

  const apply = () => {
    updateDraft((draft) => {
      if (!draft.workflow_states) draft.workflow_states = {};
      // Both lists are written so the draft states the full visibility outcome
      // for this concept, independent of what earlier overlays hide.
      draft.workflow_states[concept] = {
        hide: allStates.filter((state) => !visible[state]),
        show: allStates.filter((state) => visible[state]),
      };
    });
    onClose();
  };

  return (
    <EditorDialog title="Customize workflow states" subtitle={concept} onClose={onClose} onApply={apply}>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        Hidden states are only removed from the presentation; the current
        state of a record is always shown.
      </Typography>
      {allStates.map((state) => (
        <FormControlLabel
          key={state}
          sx={{ display: 'block' }}
          control={
            <Checkbox
              size="small"
              checked={!!visible[state]}
              onChange={(event) => setVisible((map) => ({ ...map, [state]: event.target.checked }))}
            />
          }
          label={state}
        />
      ))}
    </EditorDialog>
  );
};
"""


def generate() -> str:
    return _TEMPLATE
