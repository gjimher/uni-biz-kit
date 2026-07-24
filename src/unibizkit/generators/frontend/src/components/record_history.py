import json
from typing import Any, Dict, List

from ....backend.schema_parts.joins import _join_table_pairs
from ....backend.schema_parts.versioning import aggregate_root
from ..resources.helpers import build_m2m_config


def _config(ctx) -> Dict[str, Any]:
    history_concept = next(
        concept for concept in ctx.concepts
        if concept.get("_be_version_history")
    )
    concepts = {}
    for concept in ctx.concepts:
        if not concept.get("versioned"):
            continue
        root, hops = aggregate_root(concept["name"], ctx.concept_map)
        part_of = next((
            field for field in concept["fields"]
            if field["type"] == "relation_to_one" and field.get("subtype") == "part_of"
        ), None)
        fields = {}
        for field in concept["fields"]:
            name = field["name"]
            workflow_or_status = (
                name.startswith("status") or name.startswith("state")
            )
            structural = field.get("subtype") == "part_of"
            calculated = "calculated" in field
            reversible = (
                field["_fe_visibility"] == "editable"
                and not workflow_or_status
                and not structural
                and not calculated
                and field["type"] != "relation_to_many"
            )
            if calculated:
                reason = "Calculated field; informational only"
            elif workflow_or_status:
                reason = "State/status must be changed manually"
            elif structural:
                reason = "part_of structure is not restored automatically"
            elif field["_fe_visibility"] != "editable":
                reason = "Backend-managed field; informational only"
            else:
                reason = None
            fields[name] = {
                "label": name.replace("_", " ").capitalize(),
                "type": field["type"],
                "target": field.get("target"),
                "reversible": reversible,
                "reason": reason,
            }
        concepts[concept["name"]] = {
            "root": root,
            "hops": [
                {"concept": child, "field": field, "parent": parent}
                for child, field, parent in hops
            ],
            "recursiveParent": (
                part_of["name"] if part_of and part_of["target"] == concept["name"] else None
            ),
            "fields": fields,
        }
    relation_fields = {}
    for join_table, table1, table2 in _join_table_pairs(ctx.concepts, ctx.concept_map):
        relation_fields[join_table] = {
            f"{table1}_id": {
                "label": table1.replace("_", " ").capitalize(),
                "type": "relation_to_one",
                "target": table1,
            },
            f"{table2}_id": {
                "label": table2.replace("_", " ").capitalize(),
                "type": "relation_to_one",
                "target": table2,
            },
        }
    return {
        "historyResource": history_concept["name"],
        "concepts": concepts,
        "m2m": build_m2m_config(ctx.concepts, ctx.concept_map),
        "relationFields": relation_fields,
    }


def generate(ctx) -> str:
    config = json.dumps(_config(ctx), indent=2)
    return r'''import * as React from 'react';
import { createPortal } from 'react-dom';
import {
  Button, Pagination,
  useDataProvider, useNotify, useRecordContext,
} from 'react-admin';
import { useFormContext } from 'react-hook-form';
import {
  Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Paper, Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material';
import { History as HistoryIcon } from '@mui/icons-material';
import { ListRowActionScopeProvider } from './list_row_actions';

const CONFIG = __CONFIG__;
const PENDING_KEY = 'ubk.version.pendingRevert';
const PART_OF_REVERT_EVENT = 'ubk:part-of-revert';

export const consumePendingPartOfRevert = (concept, id) => {
  const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
  if (!pending?.partOf || pending.concept !== concept || String(pending.id) !== String(id)) return null;
  sessionStorage.removeItem(PENDING_KEY);
  return pending;
};

const display = value => {
  if (value === null) return 'null';
  if (value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
};

const changedKeys = version => {
  const values = version.operation === 'delete' ? version.before : version.changed;
  return Object.keys(values || {}).filter(key => !['id', 'id_presentation', '_created_at', '_updated_at'].includes(key));
};

const VersionValue = ({ value, field, snapshot }) => {
  const dataProvider = useDataProvider();
  const [label, setLabel] = React.useState(null);
  const snapshotLabel = snapshot?.id_presentation;
  React.useEffect(() => {
    let active = true;
    setLabel(null);
    if (value == null || field?.type !== 'relation_to_one' || !field.target || snapshotLabel) return undefined;
    dataProvider.getOne(field.target, { id: value })
      .then(({ data }) => { if (active) setLabel(data.id_presentation || `#${value}`); })
      .catch(() => { if (active) setLabel(`#${value}`); });
    return () => { active = false; };
  }, [dataProvider, field?.target, field?.type, snapshotLabel, value]);
  if (field?.type === 'relation_to_one' && value != null) return snapshotLabel || label || `#${value}`;
  return display(value);
};

export const VersionDetail = ({ version, onClose }) => {
  const [raw, setRaw] = React.useState(false);
  const metadata = CONFIG.concepts[version.concept]?.fields || CONFIG.relationFields[version.concept] || {};
  const keys = changedKeys(version);
  const close = event => {
    event?.stopPropagation();
    onClose();
  };
  return (
    <Dialog open onClick={event => event.stopPropagation()} onClose={close} fullWidth maxWidth="md">
      <DialogTitle>{version.operation} · {version.concept} · {version.concept_id_presentation}</DialogTitle>
      <DialogContent>
        <Table size="small">
          <TableHead><TableRow><TableCell>Field</TableCell><TableCell>Before</TableCell><TableCell>After</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {keys.map(key => {
              const oldValue = version.before?.[key];
              const hasNew = version.operation !== 'delete' && Object.prototype.hasOwnProperty.call(version.changed || {}, key);
              const field = metadata[key];
              return <TableRow key={key}>
                <TableCell>{field?.label || key}</TableCell>
                <TableCell sx={{ color: 'text.disabled', textDecoration: oldValue !== undefined ? 'line-through' : 'none', whiteSpace: 'pre-wrap' }}><VersionValue value={oldValue} field={field} snapshot={version.before?.[`_${key}_deleted_snapshot`]} /></TableCell>
                <TableCell sx={{ fontWeight: hasNew ? 600 : 400, whiteSpace: 'pre-wrap' }}>{hasNew ? <VersionValue value={version.changed[key]} field={field} snapshot={version.changed?.[`_${key}_deleted_snapshot`]} /> : '—'}</TableCell>
                <TableCell>{field?.reason && <Chip size="small" variant="outlined" label={field.reason} />}</TableCell>
              </TableRow>;
            })}
          </TableBody>
        </Table>
        <Button sx={{ mt: 2 }} onClick={() => setRaw(value => !value)}>{raw ? 'Hide JSON' : 'Show JSON'}</Button>
        {raw && <Paper variant="outlined" sx={{ mt: 1, p: 2, overflow: 'auto' }}><pre>{JSON.stringify({ before: version.before, changed: version.changed }, null, 2)}</pre></Paper>}
      </DialogContent>
      <DialogActions><Button onClick={close}>Close</Button></DialogActions>
    </Dialog>
  );
};

const resolveRoot = async (dataProvider, concept, record) => {
  const cfg = CONFIG.concepts[concept];
  if (!cfg) return null;
  if (cfg.recursiveParent) {
    let current = record;
    const seen = new Set();
    while (current?.[cfg.recursiveParent] && !seen.has(current.id)) {
      seen.add(current.id);
      current = (await dataProvider.getOne(concept, { id: current[cfg.recursiveParent] })).data;
    }
    return current?.id ?? record.id;
  }
  let current = record;
  for (const hop of cfg.hops) {
    const parentId = current?.[hop.field];
    if (parentId == null) return null;
    current = (await dataProvider.getOne(hop.parent, { id: parentId })).data;
  }
  return current?.id ?? record.id;
};

const writableValues = version => {
  const fields = CONFIG.concepts[version.concept]?.fields || {};
  const values = {};
  const skipped = [];
  for (const key of changedKeys(version)) {
    if (fields[key]?.reversible) values[key] = version.before?.[key] ?? null;
    else skipped.push(fields[key]?.reason || `${key} is informational only`);
  }
  return { values, skipped: [...new Set(skipped)] };
};

export const canRevertVersion = version => {
  if (version.change_type === 'relations') return ['insert', 'delete'].includes(version.operation);
  if (version.change_type !== 'fields') return false;
  return version.operation === 'update' && Object.keys(writableValues(version).values).length > 0;
};

const notifyText = (notify, message, type = 'info') => {
  notify(message, { type, messageArgs: { _: message } });
};

export const revertVersionFromList = async ({ record: version, dataProvider, notify, navigate }) => {
  if (version.change_type === 'relations') {
    const row = version.operation === 'delete' ? version.before : version.changed;
    let endpointConcept = version.root_concept;
    let relation = Object.entries(CONFIG.m2m[endpointConcept] || {})
      .find(([, cfg]) => cfg.resource === version.concept && row?.[cfg.linkField] != null);
    if (!relation) {
      for (const [candidate, links] of Object.entries(CONFIG.m2m)) {
        if (CONFIG.concepts[candidate]?.root !== version.root_concept) continue;
        const found = Object.entries(links)
          .find(([, cfg]) => cfg.resource === version.concept && row?.[cfg.linkField] != null);
        if (found) { endpointConcept = candidate; relation = found; break; }
      }
    }
    if (!relation) {
      notifyText(notify, 'This relation cannot be restored from an edit form.', 'warning');
      return null;
    }
    const [field, cfg] = relation;
    const endpointId = row?.[cfg.linkField];
    const relatedId = row?.[cfg.targetField];
    try {
      await dataProvider.getOne(endpointConcept, { id: endpointId });
    } catch (_error) {
      notifyText(notify, 'The original record no longer exists, so this relation cannot be restored.', 'warning');
      return null;
    }
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({
      concept: endpointConcept, id: endpointId,
      relation: { field, relatedId, operation: version.operation },
    }));
    navigate(endpointConcept, endpointId);
    return null;
  }

  if (version.change_type === 'fields' && version.operation === 'delete') {
    notifyText(notify, 'The original record no longer exists, so this change cannot be restored automatically. Use the detail snapshot for manual recovery.', 'warning');
    return null;
  }
  if (version.operation !== 'update' || version.change_type !== 'fields') return null;

  const id = version.concept_id;
  const { values, skipped } = writableValues(version);
  if (!Object.keys(values).length) {
    notifyText(notify, skipped[0] || 'This change is informational only.', 'warning');
    return null;
  }
  try {
    await dataProvider.getOne(version.concept, { id });
  } catch (_error) {
    notifyText(notify, 'The original record no longer exists, so this change cannot be restored.', 'warning');
    return null;
  }
  const targetConfig = CONFIG.concepts[version.concept];
  if (targetConfig?.hops?.length && targetConfig.root !== version.concept) {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({
      partOf: true, concept: version.concept, id, values, skipped,
    }));
    navigate(targetConfig.root, version.root_concept_id);
    return null;
  }
  sessionStorage.setItem(PENDING_KEY, JSON.stringify({ concept: version.concept, id, values, skipped }));
  navigate(version.concept, id);
  return null;
};

export const RecordHistoryButton = ({ concept, canRevert = false, ListComponent, buttonTargetId }) => {
  const record = useRecordContext();
  const form = useFormContext();
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const historyButtonRef = React.useRef(null);
  const [open, setOpen] = React.useState(false);
  const [rootId, setRootId] = React.useState(null);
  const [buttonTarget, setButtonTarget] = React.useState(null);
  const notifyText = React.useCallback((message, type = 'info') => {
    notify(message, { type, messageArgs: { _: message } });
  }, [notify]);
  const showRelationsTab = React.useCallback(() => {
    requestAnimationFrame(() => {
      const tabbedForm = historyButtonRef.current?.closest('main')?.querySelector('.tabbed-form');
      const relationsTab = [...(tabbedForm?.querySelectorAll('[role="tab"]') || [])]
        .find(tab => tab.textContent?.trim() === 'Relations');
      relationsTab?.click();
    });
  }, []);

  React.useEffect(() => {
    setButtonTarget(buttonTargetId ? document.getElementById(buttonTargetId) : null);
  }, [buttonTargetId]);

  React.useEffect(() => {
    if (!canRevert || !form || !record) return;
    const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
    if (!pending || pending.concept !== concept || String(pending.id) !== String(record.id)) return;
    const frame = requestAnimationFrame(() => {
      if (pending.relation) {
        const { field, relatedId, operation } = pending.relation;
        const current = form.getValues(field) || [];
        const next = operation === 'delete'
          ? [...new Set([...current, relatedId])]
          : current.filter(id => String(id) !== String(relatedId));
        form.setValue(field, next, { shouldDirty: true, shouldTouch: true });
        showRelationsTab();
      } else {
        Object.entries(pending.values).forEach(([key, value]) => form.setValue(key, value, { shouldDirty: true, shouldTouch: true }));
      }
      sessionStorage.removeItem(PENDING_KEY);
      notifyText('Previous values copied to the form. Review and save them.');
    });
    return () => cancelAnimationFrame(frame);
  }, [canRevert, concept, form, notifyText, record, showRelationsTab]);

  React.useEffect(() => {
    if (!open || !record) return;
    let active = true;
    resolveRoot(dataProvider, concept, record)
      .then(id => { if (active) setRootId(id); })
      .catch(error => notifyText(error.message, 'warning'));
    return () => { active = false; };
  }, [concept, dataProvider, notifyText, open, record]);

  const filter = rootId == null ? { id: -1 } : {
    root_concept: CONFIG.concepts[concept]?.root,
    root_concept_id: rootId,
  };

  const revert = async version => {
    if (version.change_type === 'relations') {
      const row = version.operation === 'delete' ? version.before : version.changed;
      let endpointConcept = concept;
      let relation = Object.entries(CONFIG.m2m[concept] || {}).find(([, cfg]) => cfg.resource === version.concept);
      if (!relation) {
        const currentRoot = CONFIG.concepts[concept]?.root;
        for (const [candidate, links] of Object.entries(CONFIG.m2m)) {
          if (CONFIG.concepts[candidate]?.root !== currentRoot) continue;
          const found = Object.entries(links).find(([, cfg]) => cfg.resource === version.concept && row?.[cfg.linkField] != null);
          if (found) { endpointConcept = candidate; relation = found; break; }
        }
      }
      if (!relation || !form) {
        notifyText('This relation cannot be restored from the current form.', 'warning');
        return;
      }
      const [field, cfg] = relation;
      const endpointId = row?.[cfg.linkField];
      const relatedId = row?.[cfg.targetField];
      if (endpointConcept !== concept || String(endpointId) !== String(record.id)) {
        try {
          await dataProvider.getOne(endpointConcept, { id: endpointId });
        } catch (_error) {
          notifyText('The original record no longer exists, so this relation cannot be restored.', 'warning');
          return;
        }
        sessionStorage.setItem(PENDING_KEY, JSON.stringify({
          concept: endpointConcept, id: endpointId,
          relation: { field, relatedId, operation: version.operation },
        }));
        window.location.hash = `#/admin/${endpointConcept}/${endpointId}`;
        return;
      }
      const current = form.getValues(field) || [];
      const next = version.operation === 'delete'
        ? [...new Set([...current, relatedId])]
        : current.filter(id => String(id) !== String(relatedId));
      form.setValue(field, next, { shouldDirty: true, shouldTouch: true });
      setOpen(false);
      showRelationsTab();
      return;
    }
    if (version.change_type === 'fields' && version.operation === 'delete') {
      notifyText('The original record no longer exists, so this change cannot be restored automatically. Use the detail snapshot for manual recovery.', 'warning');
      return;
    }
    if (version.operation !== 'update' || version.change_type === 'documents') return;
    const id = version.concept_id;
    const { values, skipped } = writableValues(version);
    if (!Object.keys(values).length) {
      notifyText(skipped[0] || 'This change is informational only.', 'warning');
      return;
    }
    if (version.concept === concept && String(id) === String(record.id) && form) {
      Object.entries(values).forEach(([key, value]) => form.setValue(key, value, { shouldDirty: true, shouldTouch: true }));
      if (skipped.length) notifyText(skipped.join('. '), 'warning');
      setOpen(false);
      return;
    }
    try {
      await dataProvider.getOne(version.concept, { id });
    } catch (_error) {
      notifyText('The original record no longer exists, so this change cannot be restored.', 'warning');
      return;
    }
    const targetConfig = CONFIG.concepts[version.concept];
    if (targetConfig?.hops?.length && targetConfig.root !== version.concept && rootId != null) {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({
        partOf: true, concept: version.concept, id, values, skipped,
      }));
      setOpen(false);
      if (concept === targetConfig.root && String(record.id) === String(rootId)) {
        window.dispatchEvent(new CustomEvent(PART_OF_REVERT_EVENT));
      } else {
        window.location.hash = `#/admin/${targetConfig.root}/${rootId}`;
      }
      return;
    }
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ concept: version.concept, id, values }));
    window.location.hash = `#/admin/${version.concept}/${id}`;
  };

  if (!record || !CONFIG.concepts[concept]) return null;
  const historyButton = (
    <Button ref={historyButtonRef} label="Versions" startIcon={<HistoryIcon />} onClick={() => { setRootId(null); setOpen(true); }} />
  );
  return <>
    {buttonTargetId ? (buttonTarget && createPortal(historyButton, buttonTarget)) : historyButton}
    <Dialog
      open={open}
      onClose={() => setOpen(false)}
      fullWidth
      maxWidth="xl"
      PaperProps={{ sx: { maxHeight: 'calc(100vh - 32px)' } }}
    >
      <DialogTitle>Record history</DialogTitle>
      <DialogContent sx={{ overflow: 'hidden', pt: 0 }}>
        {open && ListComponent && <ListRowActionScopeProvider value={{ canRevert, revert }}>
          <ListComponent
            resource={CONFIG.historyResource}
            filter={filter}
            sort={{ field: '_updated_at', order: 'DESC' }}
            perPage={10}
            disableSyncWithLocation
            storeKey={false}
            title={false}
            rowClick={false}
            bulkActionButtons={false}
            omit={['root_concept']}
            preferenceKey={`${CONFIG.historyResource}.record-history`}
            pagination={<Pagination rowsPerPageOptions={[10, 25, 50, 100]} />}
            sx={{
            '& .RaList-main, & .RaList-actions, & .RaList-content': {
              width: '100%',
              minWidth: 0,
              maxWidth: '100%',
            },
            '& .RaList-content': { boxShadow: 'none' },
            '& .RaDatagrid-root, & .RaDatagrid-tableWrapper': {
              width: '100%',
              minWidth: 0,
              maxWidth: '100%',
            },
            '& .RaDatagrid-tableWrapper': { overflowX: 'hidden' },
            '& table.RaDatagrid-table': {
              tableLayout: 'fixed !important',
              width: '100% !important',
              maxWidth: '100%',
            },
            '& .RaDatagrid-headerCell': {
              px: 0.75,
              py: 0.5,
              overflow: 'hidden',
              fontSize: '0.75rem',
              lineHeight: 1.2,
              whiteSpace: 'normal',
            },
            '& .RaDatagrid-headerCell .MuiButtonBase-root': {
              minWidth: 0,
              p: 0,
              fontSize: 'inherit',
              lineHeight: 'inherit',
              textAlign: 'left',
            },
            '& .RaDatagrid-rowCell': {
              px: 0.75,
              py: 0.5,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            },
            '& .column-concept': { width: '7%' },
            '& .column-concept_id_presentation': { width: '14%' },
            '& .column-root_concept': { width: '7%' },
            '& .column-root_concept_id_presentation': { width: '14%' },
            '& .column-change_type': { width: '7%' },
            '& .column-operation': { width: '7%' },
            '& .column-changed_by': { width: '11%' },
            '& .column-transaction_id': { width: '8%' },
            '& .column-_updated_at': { width: '13%' },
            '& .column-undefined': { width: '6%' },
            }}
          />
        </ListRowActionScopeProvider>}
      </DialogContent>
      <DialogActions><Button onClick={() => setOpen(false)}>Close</Button></DialogActions>
    </Dialog>
  </>;
};
'''.replace("__CONFIG__", config)
