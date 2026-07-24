import json
from typing import Iterable


def generate() -> str:
    return r'''import * as React from 'react';
import {
  useDataProvider, useNotify, usePermissions, useRecordContext,
  useRedirect, useRefresh, useResourceContext,
} from 'react-admin';
import { IconButton, Tooltip } from '@mui/material';
import { LIST_ROW_ACTIONS } from '../presentation/addons/_registry';

const ListRowActionScope = React.createContext(null);

export const ListRowActionScopeProvider = ({ value, children }) => (
  <ListRowActionScope.Provider value={value}>{children}</ListRowActionScope.Provider>
);

const resolveTooltip = (tooltip, context) => (
  typeof tooltip === 'function' ? tooltip(context) : tooltip
);

export const ListRowActions = ({ actions = [] }) => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const { permissions } = usePermissions();
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();
  const refresh = useRefresh();
  const scope = React.useContext(ListRowActionScope);
  const [overlay, setOverlay] = React.useState(null);
  const close = React.useCallback(() => setOverlay(null), []);
  const navigate = React.useCallback(
    (targetResource, id) => redirect('edit', targetResource, id),
    [redirect],
  );
  const context = React.useMemo(() => ({
    resource, record, id: record?.id, permissions, dataProvider,
    notify, navigate, refresh, close, scope,
  }), [resource, record, permissions, dataProvider, notify, navigate, refresh, close, scope]);
  const applicable = actions
    .map(name => [name, LIST_ROW_ACTIONS[name]])
    .filter(([, action]) => action && action.visible(context));

  const run = async (event, action) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      const result = await action.execute(context);
      if (React.isValidElement(result)) setOverlay(result);
    } catch (error) {
      const message = error?.message || 'List action failed';
      notify(message, { type: 'error', messageArgs: { _: message } });
    }
  };

  if (!record || (!applicable.length && !overlay)) return null;
  return <span style={{ display: 'inline-flex', alignItems: 'center' }} onClick={event => event.stopPropagation()}>
    {applicable.map(([name, action]) => {
      const Icon = action.Icon;
      const title = resolveTooltip(action.tooltip, context);
      return <Tooltip key={name} title={title}>
        <IconButton size="small" aria-label={title} onClick={event => run(event, action)}>
          <Icon fontSize="small" />
        </IconButton>
      </Tooltip>;
    })}
    {overlay}
  </span>;
};
'''


def generate_registry(action_names: Iterable[str]) -> str:
    names = sorted(set(action_names))
    imports = "\n".join(
        f"import * as action{index} from './{name}.jsx';"
        for index, name in enumerate(names)
    )
    entries = "\n".join(
        f"  {json.dumps(name)}: action{index},"
        for index, name in enumerate(names)
    )
    return f"""{imports}

export const LIST_ROW_ACTIONS = {{
{entries}
}};
"""


def generate_version_details() -> str:
    return r'''import VisibilityIcon from '@mui/icons-material/Visibility';
import { VersionDetail } from '../../components/record_history';

export const Icon = VisibilityIcon;
export const tooltip = 'Show details';
export const visible = ({ record }) => Boolean(record);
export const execute = ({ record, close }) => <VersionDetail version={record} onClose={close} />;
'''


def generate_version_revert() -> str:
    return r'''import RestoreIcon from '@mui/icons-material/Restore';
import { canRevertVersion, revertVersionFromList } from '../../components/record_history';

export const Icon = RestoreIcon;
export const tooltip = 'Revert';
export const visible = ({ record, scope }) => (
  scope?.canRevert !== false && canRevertVersion(record)
);
export const execute = context => (
  context.scope?.revert ? context.scope.revert(context.record) : revertVersionFromList(context)
);
'''
