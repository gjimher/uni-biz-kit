def generate() -> str:
    return r'''import * as React from 'react';
import { BulkDeleteButton, Button, useListContext, useNotify, usePermissions, useRecordContext, useRefresh, useResourceContext } from 'react-admin';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { supabaseClient } from '../supabaseClient';
import { BACKEND_ACTIONS } from '../backendActionsConfig';

export const ConceptActions = ({ placement, ids: explicitIds }) => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const notify = useNotify();
  const refresh = useRefresh();
  const [running, setRunning] = React.useState(null);
  const ids = explicitIds ?? (record?.id == null ? [] : [record.id]);
  const actions = (BACKEND_ACTIONS[resource] || []).filter(action => action.placement.includes(placement));
  const invoke = async (action) => {
    setRunning(action.function);
    const { data, error } = await supabaseClient.functions.invoke(action.function, { body: ids.length === 1 ? { id: ids[0] } : { ids } });
    setRunning(null);
    if (error || data?.status === 'ko') return notify(data?.message || error?.message || 'Backend action failed', { type: 'error' });
    notify(data?.message || 'Action completed successfully', { type: 'success' });
    refresh();
  };
  return actions.map(action => <Button key={`${action.function}:${action.label}`}
    label={running === action.function ? 'Running…' : action.label} onClick={() => invoke(action)}
    disabled={!ids.length || running !== null}><PlayArrowIcon /></Button>);
};

export const ConceptBulkActions = ({ allowDelete = true }) => {
  const resource = useResourceContext();
  const { selectedIds } = useListContext();
  const { permissions } = usePermissions();
  const canDelete = permissions?.[resource]?.includes('write') || permissions?.['*']?.includes('write');
  return <>
    <ConceptActions placement="list" ids={selectedIds} />
    {allowDelete && canDelete && <BulkDeleteButton mutationMode="pessimistic" />}
  </>;
};
'''
