_TEMPLATE = """import * as React from 'react';
import {
  Badge, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControl, FormControlLabel, InputLabel, MenuItem, Radio, RadioGroup,
  Select, Switch, Tooltip, Typography,
} from '@mui/material';
import { Edit as EditIcon } from '@mui/icons-material';
import { PERSONAL_DESIGNER, useCustomization } from '../components/customization';
__SUPABASE_IMPORT__import { countChanges, fetchCustomFiles, fileForOrder } from './api';
import { ACCENT, ACCENT_DARK, OrderField, RoleChips, monoSx } from './ui';
import PendingChangesDialog from './PendingChangesDialog';

// AppBar controls for design mode: the toggle, the start dialog (which file is
// being created/continued and for which roles) and the pending-changes chip.
const DesignTools = () => {
  const {
    userRoles, draft, setDraft,
    designEnabled: enabled, setDesignEnabled: setEnabled,
  } = useCustomization();
  const [start, setStart] = React.useState(null);
  const [pendingOpen, setPendingOpen] = React.useState(false);

  const beginDesign = async () => {
    if (draft) {
      // Resume the existing draft where it was left.
      setEnabled(true);
      return;
    }
    if (PERSONAL_DESIGNER) {
      // Per-user personalization: no file/roles to pick — the draft starts
      // from the user's saved design and will be saved back to it.
      __BEGIN_PERSONAL__
      return;
    }
    let data = { files: [], overlays: [] };
    try {
      data = await fetchCustomFiles();
    } catch (error) {
      // Endpoint unavailable (e.g. not the Vite dev server): the editor still
      // works, with download as the only way to persist the draft.
    }
    const usedOrders = new Set(data.overlays.map((overlay) => overlay.order));
    const firstFree = Array.from({ length: 100 }, (_, order) => order)
      .find((order) => !usedOrders.has(order));
    setStart({
      overlays: data.overlays,
      mode: 'new',
      order: String(firstFree === undefined ? 0 : firstFree).padStart(2, '0'),
      existingFile: data.files.length ? data.files[0] : '',
      // Default the customization to the current user's own roles.
      roles: userRoles,
    });
  };

  const confirmStart = () => {
    let next;
    if (start.mode === 'existing' && start.existingFile) {
      const overlay = start.overlays.find((item) => item.file === start.existingFile);
      next = {
        ...JSON.parse(JSON.stringify(overlay)),
        sourceFile: overlay.file,
        roles: start.roles,
      };
    } else {
      const order = parseInt(start.order, 10) || 0;
      next = { file: fileForOrder(order), order, roles: start.roles };
    }
    setDraft(next);
    setEnabled(true);
    setStart(null);
  };

  const toggleRole = (role) => setStart((state) => ({
    ...state,
    roles: state.roles.includes(role)
      ? state.roles.filter((item) => item !== role)
      : state.roles.concat(role),
  }));

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 1 }}>
      {enabled && draft && (
        <Tooltip title={`${draft.personal ? 'My personalization' : draft.file} — review, download or save the pending changes`}>
          <Badge badgeContent={countChanges(draft)} color="error">
            <Chip
              size="small"
              icon={<EditIcon sx={{ fontSize: 14 }} />}
              label={draft.personal
                ? 'My design'
                : `custom-${String(draft.order).padStart(2, '0')} · ${draft.roles && draft.roles.length ? draft.roles.join(', ') : 'all roles'}`}
              onClick={() => setPendingOpen(true)}
              sx={{
                bgcolor: 'background.paper', color: ACCENT_DARK, fontWeight: 600,
                '& .MuiChip-icon': { color: ACCENT },
                '&:hover': { bgcolor: '#f3e5f5' },
              }}
            />
          </Badge>
        </Tooltip>
      )}
      <Tooltip title="Design mode: customize the presentation for one or more roles">
        <FormControlLabel
          sx={{ mr: 0 }}
          control={
            <Switch
              size="small"
              checked={!!enabled}
              onChange={(event) => (event.target.checked ? beginDesign() : setEnabled(false))}
              sx={{
                '& .MuiSwitch-switchBase': { color: '#fff' },
                '& .MuiSwitch-switchBase.Mui-checked': { color: '#e1bee7' },
                '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: ACCENT, opacity: 1 },
              }}
            />
          }
          label="Design"
        />
      </Tooltip>

      {start && (
        <Dialog open onClose={() => setStart(null)} maxWidth="xs" fullWidth>
          <DialogTitle sx={{ pb: 0.5 }}>
            Design mode
            <Typography component="div" variant="caption" color="text.secondary">
              Draft a presentation customization on top of the model
            </Typography>
          </DialogTitle>
          <DialogContent>
            <RadioGroup value={start.mode} onChange={(event) => setStart({ ...start, mode: event.target.value })}>
              <FormControlLabel value="new" control={<Radio size="small" />} label="Create a new customization" />
              <Box sx={{ pl: 3.5, pb: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <OrderField
                  value={start.order}
                  onChange={(order) => setStart({ ...start, mode: 'new', order })}
                />
                <Typography variant="caption" sx={{ ...monoSx, color: 'text.secondary' }}>
                  {fileForOrder(parseInt(start.order, 10) || 0)}
                </Typography>
              </Box>
              {start.overlays.length > 0 && (
                <>
                  <FormControlLabel value="existing" control={<Radio size="small" />} label="Continue an existing file" />
                  <Box sx={{ pl: 3.5, pb: 1 }}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>File</InputLabel>
                      <Select
                        label="File"
                        value={start.existingFile}
                        onChange={(event) => {
                          const overlay = start.overlays.find((item) => item.file === event.target.value);
                          setStart({
                            ...start,
                            mode: 'existing',
                            existingFile: event.target.value,
                            roles: (overlay && overlay.roles) || [],
                          });
                        }}
                      >
                        {start.overlays.map((overlay) => (
                          <MenuItem key={overlay.file} value={overlay.file}>
                            <Typography component="span" sx={monoSx}>{overlay.file}</Typography>
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Box>
                </>
              )}
            </RadioGroup>
            <Typography variant="subtitle2" sx={{ mt: 1, mb: 0.75 }}>Applies to roles</Typography>
            <RoleChips selected={start.roles} onToggle={toggleRole} />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
              No roles selected = applies to everyone. While designing, the app
              is previewed as the selected roles.
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setStart(null)}>Cancel</Button>
            <Button
              variant="contained"
              onClick={confirmStart}
              sx={{ bgcolor: ACCENT, '&:hover': { bgcolor: ACCENT_DARK } }}
            >
              Start designing
            </Button>
          </DialogActions>
        </Dialog>
      )}

      {pendingOpen && <PendingChangesDialog onClose={() => setPendingOpen(false)} />}
    </Box>
  );
};

export default DesignTools;
"""


_BEGIN_PERSONAL_AUTH = """const { data } = await supabaseClient.auth.getSession();
      const user = data && data.session && data.session.user;
      let design = {};
      if (user) {
        const result = await supabaseClient
          .from('_design')
          .select('design')
          .eq('_security_owner_id', user.id)
          .limit(1);
        design = (result.data && result.data[0] && result.data[0].design) || {};
      }
      setDraft({ personal: true, ...design });
      setEnabled(true);"""


def generate(has_auth_provider: bool) -> str:
    if has_auth_provider:
        supabase_import = "import { supabaseClient } from '../supabaseClient';\n"
        begin_personal = _BEGIN_PERSONAL_AUTH
    else:
        # Without auth the personal designer can never be active (loader
        # validation); keep the branch compilable without supabaseClient.
        supabase_import = ""
        begin_personal = "setDraft({ personal: true });\n      setEnabled(true);"
    return (
        _TEMPLATE
        .replace("__SUPABASE_IMPORT__", supabase_import)
        .replace("__BEGIN_PERSONAL__", begin_personal)
    )
