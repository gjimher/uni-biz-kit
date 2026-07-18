_TEMPLATE = """import * as React from 'react';
import {
  Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  TextField, Typography,
} from '@mui/material';
import { ROLES } from '../customizationConfig';

// Visual identity of the design-mode chrome: a violet accent clearly distinct
// from the app's own palette, so editor controls never read as app UI.
export const ACCENT = '#8e24aa';
export const ACCENT_DARK = '#6a1b9a';

export const monoSx = { fontFamily: 'monospace', fontSize: 13 };

// Two-digit overlay number input (the NN in presentation-custom-NN.jsonc).
export const OrderField = ({ value, onChange }) => (
  <TextField
    size="small"
    label="NN"
    value={value}
    onChange={(event) => onChange(event.target.value.replace(/\\D/g, '').slice(0, 2))}
    sx={{ width: 64, '& input': { textAlign: 'center', ...monoSx } }}
  />
);

// Role selector rendered as toggleable chips; empty selection = all roles.
export const RoleChips = ({ selected, onToggle }) => (
  <Box sx={{ display: 'inline-flex', gap: 0.75, flexWrap: 'wrap' }}>
    {ROLES.map((role) => {
      const active = selected.includes(role);
      return (
        <Chip
          key={role}
          label={role}
          size="small"
          onClick={() => onToggle(role)}
          variant={active ? 'filled' : 'outlined'}
          sx={active
            ? { bgcolor: ACCENT, color: '#fff', '&:hover': { bgcolor: ACCENT_DARK } }
            : { color: 'text.secondary' }}
        />
      );
    })}
  </Box>
);

// Shared dialog frame for the design-mode editors: title with a monospace
// target subtitle, Cancel/Apply actions and optional extra actions (left side).
export const EditorDialog = ({
  title, subtitle, onClose, onApply, applyLabel = 'Apply to draft',
  extraActions = null, maxWidth = 'xs', children,
}) => (
  // Editor dialogs are mounted inside the element that hosts their badge
  // (menu rows, list action bars) and React bubbles portal events through the
  // component tree: stop clicks and keys here so typing or clicking in the
  // editor doesn't toggle/navigate the host underneath.
  <Dialog
    open
    onClose={onClose}
    maxWidth={maxWidth}
    fullWidth
    onClick={(event) => event.stopPropagation()}
    onKeyDown={(event) => event.stopPropagation()}
  >
    <DialogTitle sx={{ pb: 1 }}>
      {title}
      {subtitle && (
        <Typography component="div" variant="caption" sx={{ ...monoSx, color: 'text.secondary' }}>
          {subtitle}
        </Typography>
      )}
    </DialogTitle>
    <DialogContent>{children}</DialogContent>
    <DialogActions>
      {extraActions}
      <Box sx={{ flexGrow: 1 }} />
      <Button onClick={onClose}>Cancel</Button>
      {onApply && (
        <Button
          variant="contained"
          onClick={onApply}
          sx={{ bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT_DARK } }}
        >
          {applyLabel}
        </Button>
      )}
    </DialogActions>
  </Dialog>
);
"""


def generate() -> str:
    return _TEMPLATE
