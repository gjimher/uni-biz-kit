def generate() -> str:
    return """import * as React from 'react';
import {
    useRecordContext,
    useNotify,
    useRefresh,
    useGetIdentity
} from 'react-admin';
import { supabaseClient } from '../supabaseClient';
import {
    Autocomplete,
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Radio,
    RadioGroup,
    FormControlLabel,
    FormControl,
    TextField,
    Typography,
    Tooltip
} from '@mui/material';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useFormContext, useController } from 'react-hook-form';

// Pure per-record check, also used by the quick-edit table (one call per row).
export const workflowCanEditRecord = (workflow, record, identity) => {
    if (!workflow || !record) return true;
    const states = workflow.states;
    const currentStateName = record.state || states[0].name;
    const currentState = states.find(s => s.name === currentStateName);
    const userRoles = identity?.roles || [];
    return currentState?.owners.some(role => userRoles.includes(role)) ?? true;
};

export const useWorkflowCanEdit = (workflow, record, identity, identityLoading) => {
    if (identityLoading || !record) return true;
    return workflowCanEditRecord(workflow, record, identity);
};

// Whether the user can change the task owner in the record's current state.
export const workflowCanAssignRecord = (workflow, record, identity) => {
    if (!workflow || !record) return false;
    const states = workflow.states;
    const currentStateName = record.state || states[0].name;
    const currentState = states.find(s => s.name === currentStateName);
    const userRoles = identity?.roles || [];
    return currentState?.assigners?.some(role => userRoles.includes(role)) ?? false;
};

export const useWorkflowCanAssign = (workflow, record, identity, identityLoading) => {
    if (identityLoading || !record) return false;
    return workflowCanAssignRecord(workflow, record, identity);
};

// Form-bound task owner controls: freeSolo email autocomplete (suggestions come
// from the _user_directory discovery cache, limited to users whose roles own the
// current state) plus an "Assign to me" shortcut.
const TaskOwnerControl = ({ workflow, canAssign }) => {
    const record = useRecordContext();
    const { data: identity } = useGetIdentity();
    const { field } = useController({
        name: 'state_task_owner',
        defaultValue: record?.state_task_owner ?? null,
    });
    const [options, setOptions] = React.useState([]);

    const states = workflow.states;
    const currentStateName = record?.state || states[0].name;
    const currentState = states.find(s => s.name === currentStateName);
    const ownerRoles = React.useMemo(() => currentState?.owners || [], [currentStateName]);

    React.useEffect(() => {
        if (!canAssign) return;
        let cancelled = false;
        supabaseClient
            .from('_user_directory')
            .select('email, roles')
            .then(({ data }) => {
                if (cancelled || !data) return;
                setOptions(
                    data
                        .filter(user => (user.roles || []).some(role => ownerRoles.includes(role)))
                        .map(user => user.email)
                );
            });
        return () => { cancelled = true; };
    }, [canAssign, ownerRoles]);

    const myEmail = (identity?.email || '').toLowerCase();

    if (!canAssign) {
        if (!field.value) return null;
        return (
            <Typography variant="body2" sx={{ mt: 1 }}>
                Task owner: <strong>{field.value}</strong>
            </Typography>
        );
    }

    return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
            <Autocomplete
                freeSolo
                size="small"
                options={options}
                value={field.value || null}
                onChange={(event, value) => field.onChange(value ? value.toLowerCase() : null)}
                onInputChange={(event, value, reason) => {
                    if (reason === 'input' || reason === 'clear') {
                        field.onChange(value ? value.toLowerCase() : null);
                    }
                }}
                sx={{ minWidth: 300 }}
                renderInput={(params) => (
                    <TextField {...params} label="Task owner" placeholder="user email" />
                )}
            />
            <Button
                size="small"
                disabled={!myEmail || field.value === myEmail}
                onClick={() => field.onChange(myEmail)}
            >
                Assign to me
            </Button>
        </Box>
    );
};

export const WorkflowSelector = ({ workflow, resource, canEdit, canAssign = false }) => {
    const record = useRecordContext();
    const notify = useNotify();
    const refresh = useRefresh();
    const formContext = useFormContext();
    const isDirty = !!formContext?.formState?.isDirty;
    const [pendingState, setPendingState] = React.useState(null);
    const [transitionText, setTransitionText] = React.useState('');

    // Build a map of state name -> last transition info for that state
    const transitionByState = React.useMemo(() => {
        const map = {};
        if (!record || !record.state_info) return map;
        let transitions;
        try { transitions = typeof record.state_info === 'string' ? JSON.parse(record.state_info) : record.state_info; }
        catch { return map; }
        if (transitions?.last_transition) {
            const t = transitions.last_transition;
            const note = t.comment ? `
${t.comment}` : '';
            map[t.to_state] = `${new Date(t.changed_at).toLocaleString()}${note}`;
            return map;
        }
        if (!Array.isArray(transitions)) return map;
        for (const t of transitions) {
            const note = t.text ? `
${t.text}` : '';
            map[t.to] = `${t.user || 'Unknown'} · ${new Date(t.date).toLocaleString()}${note}`;
        }
        return map;
    }, [record]);

    if (!workflow) return null;

    const states = workflow.states;
    const currentStateName = record?.state || states[0].name;

    const handleRadioClick = (stateName) => {
        if (!canEdit || stateName === currentStateName) return;
        if (isDirty) {
            notify('Save changes before changing state', { type: 'warning' });
            return;
        }
        setPendingState(stateName);
    };

    const handleCancel = () => {
        setPendingState(null);
        setTransitionText('');
    };

    const handleConfirm = async () => {
        try {
            const { data, error } = await supabaseClient.functions.invoke('workflow-transition', {
                body: {
                    concept: resource,
                    id: record.id,
                    to_state: pendingState,
                    comment: transitionText,
                },
            });
            if (error) {
                throw error;
            }
            if (data?.ok === false) {
                notify(data.error || 'State change was rejected', { type: 'warning' });
                return;
            }

            notify('State updated', { type: 'info' });
            handleCancel();
            refresh();
        } catch (error) {
            let body = error.context;
            if (typeof body === 'string') {
                try { body = JSON.parse(body); } catch { body = null; }
            }
            notify(body?.error || error.message || 'Error updating state', { type: 'warning' });
        }
    };
    return (
        <Box sx={{ mb: 2, p: 2, border: '1px solid #ccc', borderRadius: 1, backgroundColor: '#f9f9f9' }}>
            <Typography variant="subtitle2" gutterBottom sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                Workflow State
                {workflow.description && (
                    <Tooltip title={workflow.description} placement="top">
                        <HelpOutlineIcon sx={{ fontSize: 16, cursor: 'help', color: 'text.secondary' }} />
                    </Tooltip>
                )}
            </Typography>
            <FormControl component="fieldset">
                <RadioGroup row value={currentStateName} onChange={() => {}}>
                    {states.map(s => {
                        const stateName = s.name === currentStateName ? <strong>{s.name}</strong> : s.name;
                        const stateLabel = s.description ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                {stateName}
                                <Tooltip title={s.description} placement="top">
                                    <HelpOutlineIcon sx={{ fontSize: 14, cursor: 'help', color: 'text.secondary' }} />
                                </Tooltip>
                            </span>
                        ) : stateName;
                        return (
                        <Tooltip
                            key={s.name}
                            title={transitionByState[s.name] || ''}
                            componentsProps={{ tooltip: { sx: { fontSize: '0.875rem', whiteSpace: 'pre-line' } } }}
                        >
                            <FormControlLabel
                                value={s.name}
                                control={<Radio size="small" />}
                                label={stateLabel}
                                disabled={!canEdit}
                                onClick={() => handleRadioClick(s.name)}
                            />
                        </Tooltip>
                        );
                    })}
                </RadioGroup>
            </FormControl>
            {!canEdit && record && (
                <Typography variant="caption" color="error">
                    You do not have permission to edit in this state.
                </Typography>
            )}
            {record && formContext && <TaskOwnerControl workflow={workflow} canAssign={canAssign} />}

            <Dialog open={!!pendingState} onClose={handleCancel} maxWidth="sm" fullWidth>
                <DialogTitle>{`Change state to "${pendingState}"?`}</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        fullWidth
                        multiline
                        rows={5}
                        label="Note (optional)"
                        value={transitionText}
                        onChange={(e) => setTransitionText(e.target.value)}
                        sx={{ mt: 1 }}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancel}>Cancel</Button>
                    <Button onClick={handleConfirm} variant="contained">Confirm</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
"""
