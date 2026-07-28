def generate() -> str:
    return """// ---------------------------------------------------------------------------
// style/theme.js — the look & feel of the generated backoffice (react-admin).
//
// The palette is not defined here: it is read from the design tokens in
// ./auth, so a model that rebrands the auth pages (its own
// presentation/style/auth.jsx) rebrands the backoffice with it, and both
// halves of the app — custom presentation pages and generated admin screens —
// stay coherent.
//
// To restyle only the backoffice, place your own presentation/style/theme.js
// in the model (same export): files under the model's presentation/style/
// replace the generated ones by name.
// ---------------------------------------------------------------------------
import { defaultLightTheme } from 'react-admin';
import { deepmerge } from '@mui/utils';
import { alpha } from '@mui/material/styles';
import * as tokens from './auth';

// Read defensively: a model's own auth.jsx is free to export only the tokens
// its pages use, and a missing one must fall back instead of blanking the UI.
const INK = tokens.INK ?? '#1f2937';
const MUTED = tokens.MUTED ?? '#6b7280';
const BORDER = tokens.BORDER ?? '#d1d5db';
const ACCENT = tokens.ACCENT ?? '#2563eb';
const BG = tokens.BG ?? '#f9fafb';
const FONT = tokens.FONT
  ?? '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

const SURFACE = '#ffffff';
const ACCENT_SOFT = alpha(ACCENT, 0.1);

// Merged over react-admin's own light theme, which carries invariants the
// admin UI depends on (sidebar widths, full-width inputs, checkbox paddings).
export const adminTheme = deepmerge(defaultLightTheme, {
  palette: {
    primary: { main: ACCENT, contrastText: '#fff' },
    // react-admin's AppBar defaults to color="secondary": both roles carry the
    // brand accent so no component falls back to the stock material blue.
    secondary: { main: ACCENT, contrastText: '#fff' },
    background: { default: BG, paper: SURFACE },
    text: { primary: INK, secondary: MUTED },
    divider: BORDER,
    action: { hover: alpha(ACCENT, 0.04), selected: ACCENT_SOFT },
  },
  typography: {
    fontFamily: FONT,
    button: { textTransform: 'none', fontWeight: 600 },
    h6: { fontWeight: 700 },
  },
  shape: { borderRadius: 8 },
  components: {
    // --- Frame: flat app bar and sidebar, separated by hairlines ------------
    RaAppBar: {
      // The component reads useThemeProps({ name: 'RaAppBar' }), so its
      // color prop is overridable from here.
      defaultProps: { color: 'inherit' },
      styleOverrides: {
        root: {
          backgroundColor: SURFACE,
          color: INK,
          boxShadow: 'none',
          borderBottom: `1px solid ${BORDER}`,
        },
      },
    },
    RaSidebar: {
      styleOverrides: {
        root: {
          '& .RaSidebar-paper': {
            backgroundColor: SURFACE,
            borderRight: `1px solid ${BORDER}`,
          },
        },
      },
    },
    RaMenuItemLink: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          marginRight: 8,
          marginLeft: 8,
          paddingTop: 6,
          paddingBottom: 6,
          '&.RaMenuItemLink-active': {
            color: ACCENT,
            backgroundColor: ACCENT_SOFT,
            fontWeight: 600,
            '& .RaMenuItemLink-icon': { color: ACCENT },
          },
        },
      },
    },
    // --- Surfaces: bordered cards instead of floating ones ------------------
    MuiPaper: {
      styleOverrides: {
        // Only the resting elevation: menus, popovers and dialogs keep their
        // shadow, which is what separates them from the page underneath.
        elevation1: { boxShadow: 'none', border: `1px solid ${BORDER}` },
      },
    },
    // --- Lists -------------------------------------------------------------
    RaDatagrid: {
      styleOverrides: {
        root: {
          '& .RaDatagrid-headerCell': {
            backgroundColor: BG,
            color: MUTED,
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: 0.3,
            borderBottom: `1px solid ${BORDER}`,
          },
          '& .RaDatagrid-row:hover': { backgroundColor: alpha(ACCENT, 0.04) },
        },
      },
    },
    // --- Forms -------------------------------------------------------------
    // Bordered inputs, like the ones the auth pages draw, instead of the grey
    // filled boxes react-admin defaults to.
    MuiTextField: { defaultProps: { variant: 'outlined' } },
    MuiFormControl: { defaultProps: { variant: 'outlined' } },
    RaToolbar: {
      styleOverrides: {
        root: {
          backgroundColor: 'transparent',
          borderTop: `1px solid ${BORDER}`,
        },
      },
    },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiChip: { styleOverrides: { root: { borderRadius: 4 } } },
  },
});
"""
