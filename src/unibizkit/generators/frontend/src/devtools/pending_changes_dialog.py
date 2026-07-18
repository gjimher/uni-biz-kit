_TEMPLATE = """import * as React from 'react';
import { useNotify } from 'react-admin';
import {
  Alert, Box, Button, Collapse, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, TextField, Tooltip, Typography,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  ExpandLess as ExpandLessIcon,
  ExpandMore as ExpandMoreIcon,
} from '@mui/icons-material';
import {
  draftSections, draftToFileContent, fileForOrder, saveCustomFile, summarizeDraft,
} from './api';
import { ACCENT, ACCENT_DARK, OrderField, RoleChips, monoSx } from './ui';
import { useCustomization } from '../components/customization';
__SUPABASE_IMPORT__

const SECTIONS = ['menu', 'lists', 'forms', 'labels', 'workflow_states'];

// Review/edit the pending draft: target file number, roles, description, a
// readable change summary (raw JSON behind a toggle), plus download / save /
// discard.
const PendingChangesDialog = ({ onClose }) => {
  const notify = useNotify();
  const { draft, setDraft, setDesignEnabled: setEnabled } = useCustomization();
  const [text, setText] = React.useState(() => JSON.stringify(draftSections(draft), null, 2));
  const [showJson, setShowJson] = React.useState(false);
  const [error, setError] = React.useState('');
  const [saving, setSaving] = React.useState(false);

  if (!draft) return null;

  // Parse the edited sections back into the draft; returns the next draft or
  // null (with the parse/validation error shown in the dialog).
  const applyText = () => {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch (parseError) {
      setError(`Invalid JSON: ${parseError.message}`);
      return null;
    }
    const unknown = Object.keys(parsed).filter((key) => !SECTIONS.includes(key));
    if (unknown.length) {
      setError(`Unknown sections: ${unknown.join(', ')} (allowed: ${SECTIONS.join(', ')})`);
      return null;
    }
    const next = draft.personal
      ? { personal: true }
      : {
          file: draft.file,
          order: draft.order,
          roles: draft.roles,
          ...(draft.sourceFile ? { sourceFile: draft.sourceFile } : {}),
        };
    if (!draft.personal && draft.description) next.description = draft.description;
    Object.assign(next, parsed);
    setError('');
    setDraft(next);
    return next;
  };

  const setOrder = (digits) => {
    const order = parseInt(digits, 10) || 0;
    setDraft({ ...draft, file: fileForOrder(order), order });
  };

  const toggleRole = (role) => {
    const roles = (draft.roles || []).includes(role)
      ? draft.roles.filter((item) => item !== role)
      : (draft.roles || []).concat(role);
    setDraft({ ...draft, roles });
  };

  const download = () => {
    const next = applyText();
    if (!next) return;
    const content = draft.personal
      ? JSON.stringify(draftSections(next), null, 2) + '\\n'
      : draftToFileContent(next);
    const blob = new Blob([content], { type: 'application/json' });
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(blob);
    anchor.download = draft.personal ? 'my-design.json' : next.file;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  };

  const save = async () => {
    const next = applyText();
    if (!next) return;
    setSaving(true);
    try {
      if (draft.personal) {
        __SAVE_PERSONAL__
      } else {
        // The file now holds the changes: drop the draft and reload so the
        // overlays come back from the saved model files.
        try {
          await saveCustomFile(next.file, draftToFileContent(next), {
            previousFile: next.sourceFile || null,
          });
        } catch (fileError) {
          if (fileError.status !== 409 || !window.confirm(
            `${next.file} already exists. Overwrite it with these changes?`
          )) throw fileError;
          await saveCustomFile(next.file, draftToFileContent(next), {
            previousFile: next.sourceFile || null,
            overwrite: true,
          });
        }
        notify(`Saved ${next.file} — reloading`, { type: 'info' });
      }
      setDraft(null);
      setEnabled(false);
      window.location.reload();
    } catch (saveError) {
      setError(String(saveError.message || saveError));
      setSaving(false);
    }
  };

  // Personal mode only: delete the saved design so the user is back to the
  // application defaults.
  const reset = async () => {
    setSaving(true);
    try {
      __RESET_PERSONAL__
      setDraft(null);
      setEnabled(false);
      notify('Personalization removed — reloading', { type: 'info' });
      window.location.reload();
    } catch (resetError) {
      setError(String(resetError.message || resetError));
      setSaving(false);
    }
  };

  const discard = () => {
    setDraft(null);
    setEnabled(false);
    onClose();
  };

  // Deletes one change from the draft (WYSIWYG: the app behind updates) and
  // resyncs the JSON textarea — a later save parses that text, so leaving it
  // stale would resurrect the removed change.
  const removeChange = (line) => {
    const next = JSON.parse(JSON.stringify(draft));
    line.remove(next);
    setDraft(next);
    setText(JSON.stringify(draftSections(next), null, 2));
    setError('');
  };

  const summary = summarizeDraft(draft);

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: 0.5 }}>
        Pending customization changes
        <Typography component="div" variant="caption" sx={{ ...monoSx, color: 'text.secondary' }}>
          {draft.personal ? 'your personal design' : draft.file}
        </Typography>
      </DialogTitle>
      <DialogContent>
        {!draft.personal && (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap', mt: 0.5, mb: 1.5 }}>
              <OrderField value={String(draft.order).padStart(2, '0')} onChange={setOrder} />
              <Typography variant="body2" color="text.secondary">applies to</Typography>
              <RoleChips selected={draft.roles || []} onToggle={toggleRole} />
            </Box>
            <TextField
              label="Description"
              value={draft.description || ''}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              fullWidth
              size="small"
              margin="dense"
            />
          </>
        )}
        <Typography variant="subtitle2" sx={{ mt: 1.5, mb: 0.5 }}>Changes</Typography>
        {summary.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No changes yet — click a “D” badge on a menu entry, list, field or
            workflow to customize it.
          </Typography>
        ) : (
          <Box component="ul" sx={{ m: 0, p: 0, listStyle: 'none' }}>
            {summary.map((line, index) => (
              <Box
                component="li"
                key={index}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 0.5,
                  pl: 1, borderRadius: 1, '&:hover': { bgcolor: 'action.hover' },
                }}
              >
                <Typography variant="body2" sx={{ flexGrow: 1 }}>
                  <strong>{line.what}</strong>{line.detail ? ` — ${line.detail}` : ''}
                </Typography>
                <Tooltip title="Remove this change">
                  <IconButton
                    size="small"
                    aria-label={`Remove change: ${line.what}`}
                    onClick={() => removeChange(line)}
                  >
                    <DeleteIcon fontSize="inherit" />
                  </IconButton>
                </Tooltip>
              </Box>
            ))}
          </Box>
        )}
        <Button
          size="small"
          onClick={() => setShowJson((open) => !open)}
          startIcon={showJson ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          sx={{ mt: 1, color: ACCENT }}
        >
          Edit as JSON
        </Button>
        <Collapse in={showJson}>
          <TextField
            value={text}
            onChange={(event) => setText(event.target.value)}
            onBlur={applyText}
            multiline
            minRows={8}
            maxRows={20}
            fullWidth
            sx={{ mt: 0.5, '& textarea': { ...monoSx } }}
          />
        </Collapse>
        {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button color="error" onClick={discard}>Discard draft</Button>
        {draft.personal && (
          <Button color="error" onClick={reset} disabled={saving}>
            Reset personalization
          </Button>
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose}>Close</Button>
        <Button onClick={download}>{draft.personal ? 'Download' : 'Download .jsonc'}</Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={saving}
          sx={{ bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT_DARK } }}
        >
          {draft.personal ? 'Save my design' : 'Save to model'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default PendingChangesDialog;
"""


_SAVE_PERSONAL_AUTH = """const { data } = await supabaseClient.auth.getSession();
        const user = data.session.user;
        // One row per user: the owner column is filled by the backend trigger
        // (clients may not write _-prefixed columns), and since ON CONFLICT is
        // evaluated after triggers, the unique owner column still deduplicates.
        const { error: upsertError } = await supabaseClient.from('_design').upsert(
          { user_email: user.email, design: draftSections(next) },
          { onConflict: '_security_owner_id' }
        );
        if (upsertError) throw upsertError;
        notify('Personalization saved — reloading', { type: 'info' });"""

_RESET_PERSONAL_AUTH = """const { data } = await supabaseClient.auth.getSession();
      const { error: deleteError } = await supabaseClient
        .from('_design')
        .delete()
        .eq('_security_owner_id', data.session.user.id);
      if (deleteError) throw deleteError;"""


def generate(has_auth_provider: bool) -> str:
    if has_auth_provider:
        supabase_import = "import { supabaseClient } from '../supabaseClient';\n"
        save_personal = _SAVE_PERSONAL_AUTH
        reset_personal = _RESET_PERSONAL_AUTH
    else:
        # Without auth the personal designer can never be active (loader
        # validation); keep the branches compilable without supabaseClient.
        supabase_import = ""
        save_personal = "notify('Personalization requires authentication', { type: 'warning' });"
        reset_personal = ""
    return (
        _TEMPLATE
        .replace("__SUPABASE_IMPORT__", supabase_import)
        .replace("__SAVE_PERSONAL__", save_personal)
        .replace("__RESET_PERSONAL__", reset_personal)
    )
