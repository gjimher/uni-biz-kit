_TEMPLATE = """import * as React from 'react';
import { Box, Tooltip } from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { ACCENT } from './ui';
import {
  AddMenuEntryDialog, FieldEditor, ListEditor, MenuItemEditor, WorkflowEditor,
} from './editors';

const EDITORS = {
  field: FieldEditor,
  list: ListEditor,
  menuItem: MenuItemEditor,
  menuAdd: AddMenuEntryDialog,
  workflow: WorkflowEditor,
};

// Field badges float on the input corner; menu badges sit inline in the row.
const PLACEMENTS = {
  field: { position: 'absolute', top: -2, right: -2, zIndex: 10 },
  menuItem: { ml: 0.75 },
};

// The "D" marker rendered on designable elements while design mode is active;
// clicking it opens the popup editor matching the target kind. Kept small and
// translucent until hovered so design mode stays readable.
const DesignBadge = ({ target }) => {
  const [open, setOpen] = React.useState(false);
  const Editor = EDITORS[target.kind];
  if (!Editor) return null;
  const openEditor = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setOpen(true);
  };
  const editor = open && <Editor {...target} onClose={() => setOpen(false)} />;

  // "Add entry" affordance shown at the end of each menu level.
  if (target.kind === 'menuAdd') {
    return (
      <>
        <Box
          role="button"
          aria-label="Add menu entry"
          onClick={openEditor}
          sx={{
            display: 'flex', alignItems: 'center', gap: 0.5,
            pl: target.path.length ? 4 : 2, py: 0.5,
            color: ACCENT, fontSize: 12, cursor: 'pointer',
            opacity: 0.55, '&:hover': { opacity: 1 },
          }}
        >
          <AddIcon sx={{ fontSize: 14 }} /> Add entry
        </Box>
        {editor}
      </>
    );
  }

  const label = ['Customize', target.kind, target.concept, target.field, target.name]
    .filter(Boolean).join(' ');
  return (
    <>
      <Tooltip title={label}>
        <Box
          component="span"
          role="button"
          aria-label={label}
          onClick={openEditor}
          sx={{
            ...(PLACEMENTS[target.kind] || { ml: 1 }),
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
            bgcolor: 'background.paper', border: `1px solid ${ACCENT}`,
            color: ACCENT, fontSize: 10, fontWeight: 700, lineHeight: 1,
            cursor: 'pointer', opacity: 0.55, verticalAlign: 'middle',
            transition: 'opacity 120ms, transform 120ms',
            '&:hover': { opacity: 1, transform: 'scale(1.2)', bgcolor: ACCENT, color: '#fff' },
          }}
        >
          D
        </Box>
      </Tooltip>
      {editor}
    </>
  );
};

export default DesignBadge;
"""


def generate() -> str:
    return _TEMPLATE
