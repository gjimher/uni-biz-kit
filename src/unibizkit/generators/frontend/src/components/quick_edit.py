def generate() -> str:
    return r"""import * as React from 'react';
import {
  useDataProvider, useGetIdentity, useListContext, useNotify,
  useRefresh, usePermissions, useRemoveItemsFromStore, useStore
} from 'react-admin';
import {
  Alert, Autocomplete as MuiAutocomplete, Box, Button, Checkbox, Dialog,
  DialogActions, DialogContent, DialogTitle, IconButton, MenuItem,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField as MuiTextField, Tooltip, Typography
} from '@mui/material';
import {
  AddCircleOutline as AddRowIcon,
  AddToPhotos as DuplicateRowIcon,
  CheckCircleOutline as SavedIcon,
  ContentCopy as CopyIcon,
  ContentPaste as PasteIcon,
  DeleteOutline as DeleteRowIcon,
  EditNote as QuickEditIcon,
  ErrorOutline as RowErrorIcon,
  HighlightAlt as SelectIcon,
  Lock as LockedIcon,
  PlaylistAdd as PasteInsertIcon,
  RestoreFromTrash as RestoreRowIcon,
  ViewColumn as ResetColumnsIcon
} from '@mui/icons-material';
import { QUICK_EDIT_CONFIG } from '../quickEditConfig';
import { firstValidationForSource, getValidations, optionsFor, validateRecord, FREE_ENTRY_OPTION } from '../presentation/lib/validations';
import { workflowCanEditRecord } from './workflow_selector';
import { mapWithConcurrency } from './import_export';

// Spreadsheet-like editing of the rows currently loaded in the list (same page,
// filters and sort) in a fullscreen dialog. Cells are controlled inputs chosen
// from the field's editor in QUICK_EDIT_CONFIG; changes (updates, inserts and
// deletes) are saved in one batch and server rejections (RLS, workflow state,
// constraints) are reported per row without losing other edits. Rows can be
// copied to / pasted from a spreadsheet as headerless TSV.
const PARALLEL_SAVES = 5;     // concurrent create/update/delete calls
const FK_OPTIONS_CAP = 1000;  // full option list for data_size 's' targets
const ID_COLUMN = '__id';     // pseudo-name of the Id column in the selection

// Map a raw PostgREST/Postgres error to a message a user can act on. The
// message patterns come from the generated security triggers (see
// generators/backend/schema_parts/security.py); they all use ERRCODE 42501,
// so match messages before falling back to the code.
export const friendlyServerError = (error) => {
  const body = error?.body || {};
  const message = body.message || error?.message || '';
  const code = String(body.code || error?.code || '');
  let match;
  if ((match = message.match(/Insufficient privilege for state (\w+)/)))
    return `Not editable: workflow state '${match[1]}' is owned by another role`;
  if ((match = message.match(/Permission denied for field (\w+)/)))
    return `You are not allowed to change the field '${match[1]}'`;
  if (/can only be changed by workflow[- ]transition/i.test(message))
    return 'The workflow state can only be changed with the state selector';
  if (code === '42501' || message.includes('row-level security'))
    return 'You do not have permission to save this record';
  if ((match = message.match(/duplicate key value violates unique constraint "([^"]+)"/)) || code === '23505')
    return `Duplicate value${match ? ` (${match[1]})` : ''} — another record already uses it`;
  if (code === '23503')
    return 'A referenced record does not exist or is still referenced';
  if ((match = message.match(/null value in column "(\w+)"/)) || code === '23502')
    return match ? `The field '${match[1]}' is required` : 'A required field is missing';
  if ((match = message.match(/violates check constraint "([^"]+)"/)) || code === '23514')
    return `The values break the data rule${match ? ` '${match[1]}'` : ''}`;
  return message || 'Unknown error';
};

// Record value -> controlled-input value (dates/datetimes as <input> strings).
const toInputValue = (field, value) => {
  if (field.editor === 'checkbox') return !!value;
  if (value === null || value === undefined) return '';
  if (field.editor === 'date') return String(value).slice(0, 10);
  if (field.editor === 'datetime') {
    const date = new Date(value);
    if (isNaN(date)) return '';
    const pad = (n) => String(n).padStart(2, '0');
    const seconds = field.precision === 'second' ? `:${pad(date.getSeconds())}` : '';
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}${seconds}`;
  }
  return value;
};

const toServerValue = (field, value) => {
  if (field.editor === 'checkbox') return !!value;
  if (value === '' || value === null || value === undefined) return null;
  if (field.editor === 'number') return Number(value);
  if (field.editor === 'datetime') return new Date(value).toISOString();
  return value;
};

const readonlyCellText = (field, value, fkLabels) => {
  if (value === null || value === undefined || value === '') return '';
  if (field.type === 'relation_to_one') return fkLabels[field.name]?.[String(value)] ?? String(value);
  if (field.money) return new Intl.NumberFormat(field.money.locale, { style: 'currency', currency: field.money.currency }).format(value);
  if (field.type === 'date') return new Date(value).toLocaleDateString();
  if (field.type === 'datetime') return new Date(value).toLocaleString();
  if (field.type === 'boolean') return value ? 'yes' : 'no';
  return String(value);
};

const columnLabel = (field) =>
  field.name.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())
  + (field.requiredForCreate ? ' *' : '');

// Narrow editors get narrow columns, so the table stays close to the list's
// footprint (rows are kept compact through small inputs and cell padding).
const columnMinWidth = (field) => {
  switch (field.editor) {
    case 'checkbox': return 60;
    case 'number': return 90;
    case 'select': return 110;
    case 'date': return 130;
    case 'reference': return 140;
    case 'datetime': return 180;
    case 'multiline': return 260; // wide enough to usually stay on one line
    default: return 150;
  }
};

// Headerless TSV, so a column can be copied over a different one.
const parseTsv = (text) => {
  const lines = text.replace(/\r/g, '').split('\n');
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines.map((line) => line.split('\t'));
};

// FK cell with server-side search, for reference targets too big to preload
// (data_size 'm'/'l'). Same lookup filter as the list search: id_presentation@ilike.
const FK_AUTOCOMPLETE_CELL = ({ field, value, label, disabled, error, onChange }) => {
  const dataProvider = useDataProvider();
  const [options, setOptions] = React.useState([]);
  const timer = React.useRef();
  const search = (query) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const { data } = await dataProvider.getList(field.target, {
          filter: query ? { 'id_presentation@ilike': `%${query}%` } : {},
          pagination: { page: 1, perPage: 25 },
          sort: { field: 'id_presentation', order: 'ASC' },
        });
        setOptions(data);
      } catch {
        // lookup failures just leave the previous options
      }
    }, 300);
  };
  const selected = value === null || value === undefined || value === ''
    ? null
    : options.find((option) => option.id === value) ?? { id: value, id_presentation: label ?? String(value) };
  return (
    <MuiAutocomplete
      size="small"
      options={options}
      value={selected}
      disabled={disabled}
      getOptionLabel={(option) => option.id_presentation ?? ''}
      isOptionEqualToValue={(option, current) => option.id === current.id}
      filterOptions={(x) => x}
      onOpen={() => search('')}
      onInputChange={(_event, query, reason) => { if (reason === 'input') search(query); }}
      onChange={(_event, option) => onChange(option ? option.id : null, option ? option.id_presentation : undefined)}
      renderInput={(params) => (
        <MuiTextField {...params} variant="standard" size="small" error={!!error} helperText={error || undefined} />
      )}
    />
  );
};

// Controlled variant of the form RELATED_VALIDATION_INPUT_* components: options
// narrowed by the row's other values; coherent auto-fill happens in setCell.
// Clearing semantics: the X button clears the field AND its dependent group
// columns; emptying the text clears only this field; picking the free-entry
// option leaves the field empty and focused for typing.
const VALIDATION_CELL = ({ resource, field, values, error, disabled, onSet, onClearGroup }) => {
  const validation = firstValidationForSource(resource, field.name);
  const currentValue = values[field.name] ?? '';
  const { options } = validation ? optionsFor(validation, field.name, values) : { options: [FREE_ENTRY_OPTION] };
  return (
    <MuiAutocomplete
      freeSolo
      size="small"
      options={options}
      value={currentValue}
      inputValue={currentValue}
      disabled={disabled}
      onChange={(_event, value) => onSet(value === FREE_ENTRY_OPTION ? '' : (value ?? ''))}
      onInputChange={(_event, value, reason) => {
        if (reason === 'input') onSet(value === FREE_ENTRY_OPTION ? '' : (value ?? ''));
      }}
      componentsProps={{
        clearIndicator: {
          onClick: (event) => {
            event.preventDefault();
            event.stopPropagation();
            onClearGroup();
          },
        },
      }}
      renderInput={(params) => (
        <MuiTextField {...params} variant="standard" size="small" error={!!error} helperText={error || undefined} />
      )}
    />
  );
};

const QUICK_EDIT_DIALOG = ({ resource, config, records, onClose }) => {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const refresh = useRefresh();
  const { permissions } = usePermissions();
  const { identity } = useGetIdentity();
  const [columns, setColumns] = useStore(`preferences.${resource}.datagrid.columns`);
  const [availableColumns] = useStore(`preferences.${resource}.datagrid.availableColumns`, []);
  const [omit] = useStore(`preferences.${resource}.datagrid.omit`, []);

  const initialValues = (record) => {
    const values = {};
    for (const field of config.fields) values[field.name] = toInputValue(field, record[field.name]);
    return values;
  };
  const emptyValues = () => {
    const values = {};
    for (const field of config.fields) values[field.name] = field.editor === 'checkbox' ? false : '';
    return values;
  };
  const newRowSeq = React.useRef(0);
  const makeNewRow = () => {
    newRowSeq.current += 1;
    return {
      key: `new-${newRowSeq.current}`,
      record: null,
      values: emptyValues(),
      dirtyFields: {},
      clientErrors: {},
      pasteErrors: {},
      serverError: null,
      saved: false,
      deleted: false,
    };
  };

  // The table edits exactly the rows the list has loaded: same page, filters
  // and sort. To edit other rows, page or filter the list and reopen.
  const [rows, setRows] = React.useState(() => records.map((record) => ({
    key: `id-${record.id}`,
    record,
    values: initialValues(record),
    dirtyFields: {},
    clientErrors: {},
    pasteErrors: {},
    serverError: null,
    saved: false,
    deleted: false,
  })));
  const [fkLabels, setFkLabels] = React.useState({});
  const [fkOptions, setFkOptions] = React.useState({});
  const [saving, setSaving] = React.useState(false);
  const [confirmDiscard, setConfirmDiscard] = React.useState(false);
  const [selectMode, setSelectMode] = React.useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = React.useState(new Set());
  const [selectedColNames, setSelectedColNames] = React.useState(new Set());
  const [pasteCapture, setPasteCapture] = React.useState(null);
  const columnsSynced = React.useRef(false);

  const fieldByName = React.useMemo(
    () => Object.fromEntries(config.fields.map((field) => [field.name, field])),
    [config]
  );

  // Columns currently visible in the list view (the DatagridConfigurable
  // preference), falling back to the generated defaults.
  const visibleSources = React.useMemo(() => {
    if (availableColumns.length) {
      const sources = columns
        ? columns.map((index) => availableColumns.find((column) => column.index === index)?.source)
        : availableColumns.filter((column) => !(omit ?? []).includes(column.source)).map((column) => column.source);
      return sources.filter(Boolean);
    }
    return config.defaultColumns;
  }, [columns, availableColumns, omit, config]);

  // The Id column follows the list's column selection like any other column.
  const showIdColumn = visibleSources.includes('id_presentation');

  // When rows can be created inline, the table always shows every
  // required-for-create field regardless of the user's column selection.
  const tableFields = React.useMemo(() => {
    const names = visibleSources.filter((name) => name !== 'id_presentation' && fieldByName[name]);
    if (config.canCreate) {
      for (const field of config.fields) {
        if (field.requiredForCreate && !names.includes(field.name)) names.push(field.name);
      }
    }
    return names.map((name) => fieldByName[name]);
  }, [visibleSources, fieldByName, config]);

  // Persist the auto-added required columns so the list view matches the table.
  React.useEffect(() => {
    if (columnsSynced.current || !config.canCreate || !availableColumns.length) return;
    columnsSynced.current = true;
    const missing = config.fields.filter(
      (field) => field.requiredForCreate && !visibleSources.includes(field.name)
    );
    if (!missing.length) return;
    const currentIndexes = columns
      ?? availableColumns.filter((column) => !(omit ?? []).includes(column.source)).map((column) => column.index);
    const missingIndexes = missing
      .map((field) => availableColumns.find((column) => column.source === field.name)?.index)
      .filter(Boolean);
    if (missingIndexes.length) {
      setColumns([...currentIndexes, ...missingIndexes]);
      notify(`Added required columns: ${missing.map((field) => field.name).join(', ')}`, { type: 'info' });
    }
  }, [availableColumns]);

  // FK labels for the loaded rows, plus full option lists for small targets.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const referenceFields = config.fields.filter((field) => field.type === 'relation_to_one');
        const labels = {};
        const options = {};
        await Promise.all(referenceFields.map(async (field) => {
          const map = {};
          if (field.editor === 'reference' && field.targetSize === 's') {
            const result = await dataProvider.getList(field.target, {
              filter: {},
              sort: { field: 'id_presentation', order: 'ASC' },
              pagination: { page: 1, perPage: FK_OPTIONS_CAP },
            });
            options[field.name] = result.data;
            for (const record of result.data) map[String(record.id)] = record.id_presentation;
          }
          const ids = [...new Set(records.map((record) => record[field.name])
            .filter((id) => id !== null && id !== undefined))]
            .filter((id) => !(String(id) in map));
          if (ids.length) {
            const result = await dataProvider.getMany(field.target, { ids });
            for (const record of result.data) map[String(record.id)] = record.id_presentation;
          }
          labels[field.name] = map;
        }));
        if (cancelled) return;
        setFkLabels(labels);
        setFkOptions(options);
      } catch (error) {
        if (!cancelled) notify(friendlyServerError(error), { type: 'warning' });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const rowCanEdit = (row) => !row.record || workflowCanEditRecord(config.workflow, row.record, identity);
  const isDirty = (row) => !row.record || row.deleted || Object.keys(row.dirtyFields).length > 0;
  // Same per-field permission rule as the generated form inputs.
  const fieldWritable = (field) => !permissions || !!permissions[`${resource}.${field.name}`]?.includes('write');

  const rememberFkLabel = (fieldName, id, label) => {
    if (id === null || label === undefined) return;
    setFkLabels((previous) => ({
      ...previous,
      [fieldName]: { ...previous[fieldName], [String(id)]: label },
    }));
  };

  // Set one cell, then auto-fill any empty column of the same CSV validation
  // group that is left with a single coherent option (e.g. Bilbao -> Bizkaia).
  const setCell = (rowKey, fieldName, value) => setRows((rows) => rows.map((row) => {
    if (row.key !== rowKey) return row;
    const values = { ...row.values, [fieldName]: value };
    const dirtyFields = { ...row.dirtyFields, [fieldName]: true };
    const pasteErrors = { ...row.pasteErrors };
    delete pasteErrors[fieldName];
    const validation = firstValidationForSource(resource, fieldName);
    if (validation) {
      let changed = true;
      while (changed) {
        changed = false;
        for (const column of validation.columns) {
          if (values[column]) continue;
          const { options } = optionsFor(validation, column, values);
          const concrete = options.filter((option) => option !== FREE_ENTRY_OPTION);
          if (options.length === 1 && concrete.length === 1) {
            values[column] = concrete[0];
            dirtyFields[column] = true;
            changed = true;
          }
        }
      }
    }
    return { ...row, values, dirtyFields, pasteErrors, serverError: null, saved: false };
  }));

  const clearValidationGroup = (rowKey, fieldName) => setRows((rows) => rows.map((row) => {
    if (row.key !== rowKey) return row;
    const validation = firstValidationForSource(resource, fieldName);
    const columnsToClear = validation ? validation.columns : [fieldName];
    const values = { ...row.values };
    const dirtyFields = { ...row.dirtyFields };
    const pasteErrors = { ...row.pasteErrors };
    for (const column of columnsToClear) {
      values[column] = '';
      dirtyFields[column] = true;
      delete pasteErrors[column];
    }
    return { ...row, values, dirtyFields, pasteErrors, serverError: null, saved: false };
  }));

  const addRow = () => setRows((rows) => [...rows, makeNewRow()]);

  const duplicateRow = (sourceRow) => {
    const row = makeNewRow();
    for (const field of config.fields) {
      if (field.editor === 'readonly') continue;
      row.values[field.name] = sourceRow.values[field.name];
    }
    setRows((rows) => [...rows, row]);
  };

  // New rows are removed outright; existing rows are marked and deleted on save.
  const toggleDeleteRow = (targetRow) => {
    if (!targetRow.record) {
      setRows((rows) => rows.filter((row) => row.key !== targetRow.key));
      return;
    }
    setRows((rows) => rows.map((row) => (
      row.key === targetRow.key ? { ...row, deleted: !row.deleted, serverError: null, saved: false } : row
    )));
  };

  // ---- clipboard (headerless TSV; a full Copy prepends the Id column, and a
  // pasted grid one column wider than its target drops that first column) ----

  const activeFields = () => (selectMode
    ? tableFields.filter((field) => selectedColNames.has(field.name))
    : tableFields);
  const activeRowList = () => (selectMode
    ? rows.filter((row) => selectedRowKeys.has(row.key))
    : rows);
  const copyIncludesId = () => (selectMode ? selectedColNames.has(ID_COLUMN) : showIdColumn);

  const cellText = (row, field) => {
    const value = row.values[field.name];
    if (value === null || value === undefined) return '';
    if (field.editor === 'checkbox') return value ? 'true' : 'false';
    if (field.type === 'relation_to_one') return value === '' ? '' : (fkLabels[field.name]?.[String(value)] ?? String(value));
    return String(value);
  };

  const copyGrid = async () => {
    const fields = activeFields();
    const lines = activeRowList().map((row) => {
      const cells = fields.map((field) => cellText(row, field));
      if (copyIncludesId()) cells.unshift(row.record ? row.record.id_presentation : '');
      return cells.join('\t');
    });
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      notify(`Copied ${lines.length} row(s) to the clipboard`, { type: 'info' });
    } catch {
      notify('Could not write to the clipboard', { type: 'warning' });
    }
  };

  const allColNames = () => [
    ...(showIdColumn ? [ID_COLUMN] : []),
    ...tableFields.map((field) => field.name),
  ];

  const toggleSelectMode = () => {
    if (!selectMode) {
      setSelectedRowKeys(new Set(rows.map((row) => row.key)));
      setSelectedColNames(new Set(allColNames()));
    }
    setSelectMode(!selectMode);
  };
  const selectedRowCount = rows.filter((row) => selectedRowKeys.has(row.key)).length;
  const selectedColCount = allColNames().filter((name) => selectedColNames.has(name)).length;
  const toggleAllRows = () => setSelectedRowKeys(
    selectedRowCount === rows.length ? new Set() : new Set(rows.map((row) => row.key))
  );
  const toggleAllCols = () => setSelectedColNames(
    selectedColCount === allColNames().length ? new Set() : new Set(allColNames())
  );
  const toggleSelectedRow = (key) => setSelectedRowKeys((previous) => {
    const next = new Set(previous);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const toggleSelectedCol = (name) => setSelectedColNames((previous) => {
    const next = new Set(previous);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });

  // Try the native clipboard first. The browser may pop its own confirmation
  // (Firefox's floating "Paste" button, Chrome's permission bubble) and leave
  // the read pending — after a moment a notification tells the user what to
  // look for. A repeated click rejects the pending read and falls back to the
  // Ctrl+V capture dialog. pasteSeq drops a stale native read that resolves
  // after a newer attempt already handled the paste.
  const pasteSeq = React.useRef(0);
  const requestPaste = async (insert) => {
    const seq = ++pasteSeq.current;
    const hint = setTimeout(() => notify(
      'Waiting for the clipboard — confirm the browser paste prompt, or click Paste again',
      { type: 'info' }
    ), 500);
    try {
      const text = await navigator.clipboard.readText();
      if (seq === pasteSeq.current) applyPasteText(text, insert);
    } catch {
      if (seq === pasteSeq.current) setPasteCapture({ insert });
    } finally {
      clearTimeout(hint);
    }
  };

  const applyPasteText = async (text, insert) => {
    const grid = parseTsv(text);
    if (!grid.length) {
      notify('The clipboard is empty', { type: 'warning' });
      return;
    }
    const width = grid[0].length;
    if (grid.some((cells) => cells.length !== width)) {
      notify('The clipboard rows do not all have the same number of columns', { type: 'warning' });
      return;
    }
    const fields = insert ? tableFields : activeFields();
    let startCol = 0;
    if (width === fields.length + 1) startCol = 1; // leading Id column from a full Copy
    else if (width !== fields.length) {
      notify(`The clipboard has ${width} column(s) but the target expects ${fields.length}`, { type: 'warning' });
      return;
    }
    const targets = insert ? [] : activeRowList().filter((row) => !row.deleted);
    if (!insert && grid.length !== targets.length) {
      notify(`The clipboard has ${grid.length} row(s) but the target expects ${targets.length}`, { type: 'warning' });
      return;
    }

    // Resolve pasted FK labels to ids: preloaded options first, then one
    // exact id_presentation lookup per unique label (like the CSV import).
    const wantKey = (field, label) => `${field.name}::${label}`;
    const wants = [];
    grid.forEach((cells) => fields.forEach((field, index) => {
      if (field.type !== 'relation_to_one' || field.editor === 'readonly') return;
      const raw = cells[startCol + index];
      const label = raw.trim();
      if (!label) return;
      if (!wants.some((want) => wantKey(want.field, want.label) === wantKey(field, label))) {
        wants.push({ field, label, raw });
      }
    }));
    const fkResolved = {};
    await Promise.all(wants.map(async ({ field, label, raw }) => {
      const key = wantKey(field, label);
      // Labels match ignoring surrounding whitespace: recursive
      // id_presentations carry a leading separator (e.g. ' / Electronics').
      const local = (fkOptions[field.name] ?? []).filter(
        (option) => String(option.id_presentation ?? '').trim() === label
      );
      if (local.length === 1) {
        fkResolved[key] = { id: local[0].id };
        return;
      }
      if (local.length > 1) {
        fkResolved[key] = { error: `Ambiguous ${field.target} '${label}'` };
        return;
      }
      try {
        // Exact server lookup with the untrimmed cell first (it is what the
        // database stores), then with the trimmed label.
        let { data } = await dataProvider.getList(field.target, {
          filter: { id_presentation: raw },
          pagination: { page: 1, perPage: 2 },
          sort: { field: 'id', order: 'ASC' },
        });
        if (!data.length && raw !== label) {
          ({ data } = await dataProvider.getList(field.target, {
            filter: { id_presentation: label },
            pagination: { page: 1, perPage: 2 },
            sort: { field: 'id', order: 'ASC' },
          }));
        }
        if (data.length === 1) {
          fkResolved[key] = { id: data[0].id };
          rememberFkLabel(field.name, data[0].id, data[0].id_presentation);
        } else {
          fkResolved[key] = { error: data.length ? `Ambiguous ${field.target} '${label}'` : `Unknown ${field.target} '${label}'` };
        }
      } catch {
        fkResolved[key] = { error: `Could not resolve ${field.target} '${label}'` };
      }
    }));

    const parseCell = (field, raw) => {
      const trimmed = raw.trim();
      if (field.editor === 'checkbox') {
        const lower = trimmed.toLowerCase();
        if (lower === 'true' || lower === '1') return { value: true };
        if (lower === 'false' || lower === '0' || lower === '') return { value: false };
        return { error: `Not a boolean: '${trimmed}'` };
      }
      if (trimmed === '') return { value: '' };
      if (field.editor === 'number') {
        const number = Number(trimmed.replace(',', '.'));
        return isNaN(number) ? { error: `Not a number: '${trimmed}'` } : { value: String(number) };
      }
      if (field.editor === 'select') {
        return field.values.includes(trimmed) ? { value: trimmed } : { error: `Unknown value '${trimmed}'` };
      }
      if (field.type === 'relation_to_one') {
        const hit = fkResolved[wantKey(field, trimmed)];
        return hit?.error ? { error: hit.error } : { value: hit.id };
      }
      if (field.editor === 'date') {
        if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return { value: trimmed };
        const date = new Date(trimmed);
        return isNaN(date) ? { error: `Not a date: '${trimmed}'` } : { value: toInputValue(field, date.toISOString()) };
      }
      if (field.editor === 'datetime') {
        const value = toInputValue(field, trimmed);
        return value === '' ? { error: `Not a date: '${trimmed}'` } : { value };
      }
      return { value: raw };
    };

    if (insert) {
      const newRows = grid.map((cells) => {
        const row = makeNewRow();
        fields.forEach((field, index) => {
          if (field.editor === 'readonly' || !fieldWritable(field)) return;
          const parsed = parseCell(field, cells[startCol + index]);
          if (parsed.error) row.pasteErrors[field.name] = parsed.error;
          else row.values[field.name] = parsed.value;
        });
        return row;
      });
      setRows((rows) => [...rows, ...newRows]);
      notify(`${newRows.length} row(s) inserted from the clipboard — review and Save all`, { type: 'info' });
      return;
    }

    const patchByKey = {};
    targets.forEach((target, rowIndex) => {
      if (!rowCanEdit(target)) return; // locked rows are left untouched
      const patch = { values: {}, dirty: {}, errors: {} };
      fields.forEach((field, index) => {
        if (field.editor === 'readonly' || !fieldWritable(field)) return;
        const parsed = parseCell(field, grid[rowIndex][startCol + index]);
        if (parsed.error) patch.errors[field.name] = parsed.error;
        // Loose comparison: cell values may hold numbers where the parsed
        // clipboard text is a string ("30" vs 30 is not a change).
        else if (String(parsed.value ?? '') !== String(target.values[field.name] ?? '')) {
          patch.values[field.name] = parsed.value;
          patch.dirty[field.name] = true;
        }
      });
      patchByKey[target.key] = patch;
    });
    setRows((rows) => rows.map((row) => {
      const patch = patchByKey[row.key];
      if (!patch) return row;
      return {
        ...row,
        values: { ...row.values, ...patch.values },
        dirtyFields: { ...row.dirtyFields, ...patch.dirty },
        pasteErrors: { ...row.pasteErrors, ...patch.errors },
        serverError: null,
        saved: false,
      };
    }));
    notify('Clipboard values applied — review and Save all', { type: 'info' });
  };

  const saveAll = async () => {
    setSaving(true);
    const writable = config.fields.filter((field) => field.editor !== 'readonly');
    // Client-side validation first: required fields plus CSV validation groups.
    // Invalid rows are flagged and skipped; valid rows are saved anyway.
    // On updates only the touched fields and their validation groups count, so a
    // pre-existing invalid combination in untouched (or read-only prefill)
    // columns does not block saving an unrelated change.
    const relevantErrorFields = (row) => {
      const relevant = new Set(Object.keys(row.dirtyFields));
      for (const validation of getValidations(resource)) {
        if (validation.columns.some((column) => row.dirtyFields[column])) {
          for (const column of validation.columns) relevant.add(column);
        }
      }
      return relevant;
    };
    const validated = rows.map((row) => {
      if (!isDirty(row) || row.deleted) return { ...row, clientErrors: {} };
      const requiredFields = row.record
        ? writable.filter((field) => field.required && row.dirtyFields[field.name]).map((field) => field.name)
        : writable.filter((field) => field.requiredForCreate).map((field) => field.name);
      let clientErrors = validateRecord(resource, row.values, requiredFields);
      if (row.record) {
        const relevant = relevantErrorFields(row);
        clientErrors = Object.fromEntries(
          Object.entries(clientErrors).filter(([field]) => relevant.has(field))
        );
      }
      return { ...row, clientErrors };
    });
    const toSave = validated.filter((row) => isDirty(row)
      && Object.keys(row.clientErrors).length === 0
      && Object.keys(row.pasteErrors).length === 0);
    const results = {};
    await mapWithConcurrency(toSave, PARALLEL_SAVES, async (row) => {
      try {
        if (row.deleted) {
          await dataProvider.delete(resource, { id: row.record.id, previousData: row.record });
          results[row.key] = { deleted: true };
        } else if (row.record) {
          const dirty = writable.filter((field) => row.dirtyFields[field.name]);
          const data = Object.fromEntries(dirty.map((field) => [field.name, toServerValue(field, row.values[field.name])]));
          const result = await dataProvider.update(resource, { id: row.record.id, data, previousData: row.record });
          results[row.key] = { record: result.data };
        } else {
          const data = {};
          for (const field of writable) {
            const value = toServerValue(field, row.values[field.name]);
            if (value !== null) data[field.name] = value; // empty cells fall back to DB defaults
          }
          const result = await dataProvider.create(resource, { data });
          results[row.key] = { record: result.data };
        }
      } catch (error) {
        results[row.key] = { error: friendlyServerError(error) };
      }
    });
    const next = validated.map((row) => {
      const result = results[row.key];
      if (!result) return row;
      if (result.error) return { ...row, serverError: result.error };
      if (result.deleted) return null;
      return {
        ...row,
        record: result.record,
        values: initialValues(result.record),
        dirtyFields: {},
        clientErrors: {},
        pasteErrors: {},
        serverError: null,
        saved: true,
        deleted: false,
      };
    }).filter(Boolean);
    setRows(next);
    setSaving(false);
    refresh();
    const failed = next.filter((row) => row.serverError
      || Object.keys(row.clientErrors).length > 0
      || Object.keys(row.pasteErrors).length > 0).length;
    if (failed === 0) {
      if (toSave.length) notify(`${toSave.length} row(s) saved`, { type: 'info' });
      onClose();
    } else {
      notify(`${failed} row(s) could not be saved — see the row messages`, { type: 'warning' });
    }
  };

  const requestClose = () => {
    if (rows.some(isDirty)) setConfirmDiscard(true);
    else onClose();
  };

  const rowStatus = (row) => {
    if (!rowCanEdit(row)) {
      const state = row.record?.state || config.workflow?.states?.[0]?.name;
      return (
        <Tooltip title={`Read-only: workflow state '${state}' is owned by another role`}>
          <LockedIcon fontSize="small" color="disabled" />
        </Tooltip>
      );
    }
    if (row.serverError) {
      return <Tooltip title={row.serverError}><RowErrorIcon fontSize="small" color="error" /></Tooltip>;
    }
    const clientError = Object.values({ ...row.clientErrors, ...row.pasteErrors })[0];
    if (clientError) {
      return <Tooltip title={clientError}><RowErrorIcon fontSize="small" color="warning" /></Tooltip>;
    }
    if (row.deleted) {
      return <Tooltip title="Will be deleted on Save all"><DeleteRowIcon fontSize="small" color="error" /></Tooltip>;
    }
    if (isDirty(row)) {
      return <Tooltip title="Unsaved changes"><Typography component="span" color="warning.main">●</Typography></Tooltip>;
    }
    if (row.saved) {
      return <Tooltip title="Saved"><SavedIcon fontSize="small" color="success" /></Tooltip>;
    }
    return null;
  };

  const rowActions = (row) => (
    <>
      {config.canCreate && (
        <Tooltip title="Duplicate as a new row">
          <span>
            <IconButton size="small" disabled={saving} onClick={() => duplicateRow(row)}>
              <DuplicateRowIcon fontSize="inherit" />
            </IconButton>
          </span>
        </Tooltip>
      )}
      {(!row.record || rowCanEdit(row)) && (
        <Tooltip title={row.deleted ? 'Undo delete' : (row.record ? 'Delete on Save all' : 'Remove row')}>
          <span>
            <IconButton size="small" disabled={saving} onClick={() => toggleDeleteRow(row)}>
              {row.deleted ? <RestoreRowIcon fontSize="inherit" /> : <DeleteRowIcon fontSize="inherit" />}
            </IconButton>
          </span>
        </Tooltip>
      )}
    </>
  );

  const renderCell = (row, field) => {
    const value = row.values[field.name];
    const error = row.clientErrors?.[field.name] || row.pasteErrors?.[field.name];
    const disabled = saving || row.deleted || !rowCanEdit(row) || !fieldWritable(field);
    const commonProps = {
      variant: 'standard',
      size: 'small',
      fullWidth: true,
      value: value ?? '',
      error: !!error,
      helperText: error || undefined,
      disabled,
      onChange: (event) => setCell(row.key, field.name, event.target.value),
    };
    switch (field.editor) {
      case 'readonly':
        return (
          <Typography variant="body2" color="text.secondary">
            {readonlyCellText(field, value, fkLabels)}
          </Typography>
        );
      case 'checkbox':
        return (
          <>
            <Checkbox
              size="small"
              sx={{ p: 0.5 }}
              checked={!!value}
              disabled={disabled}
              onChange={(event) => setCell(row.key, field.name, event.target.checked)}
            />
            {error && (
              <Typography variant="caption" color="error" display="block">{error}</Typography>
            )}
          </>
        );
      case 'select':
        return (
          <MuiTextField select {...commonProps}>
            <MenuItem value="">&nbsp;</MenuItem>
            {field.values.map((choice) => <MenuItem key={choice} value={choice}>{choice}</MenuItem>)}
          </MuiTextField>
        );
      case 'reference': {
        if (field.targetSize === 's') {
          const options = fkOptions[field.name] ?? [];
          return (
            <MuiTextField select {...commonProps}
              onChange={(event) => setCell(row.key, field.name, event.target.value === '' ? null : event.target.value)}
            >
              <MenuItem value="">&nbsp;</MenuItem>
              {options.map((option) => <MenuItem key={option.id} value={option.id}>{option.id_presentation}</MenuItem>)}
            </MuiTextField>
          );
        }
        return (
          <FK_AUTOCOMPLETE_CELL
            field={field}
            value={value === '' ? null : value}
            label={value === '' || value === null ? undefined : fkLabels[field.name]?.[String(value)]}
            disabled={disabled}
            error={error}
            onChange={(id, label) => {
              rememberFkLabel(field.name, id, label);
              setCell(row.key, field.name, id);
            }}
          />
        );
      }
      case 'validation':
        return (
          <VALIDATION_CELL
            resource={resource}
            field={field}
            values={row.values}
            error={error}
            disabled={disabled}
            onSet={(newValue) => setCell(row.key, field.name, newValue)}
            onClearGroup={() => clearValidationGroup(row.key, field.name)}
          />
        );
      case 'number':
        return <MuiTextField type="number" {...commonProps} />;
      case 'date':
        return <MuiTextField type="date" {...commonProps} />;
      case 'datetime':
        return <MuiTextField type="datetime-local" inputProps={{ step: field.precision === 'second' ? 1 : 60 }} {...commonProps} />;
      case 'multiline':
        return <MuiTextField multiline maxRows={4} {...commonProps} />;
      default:
        return <MuiTextField {...commonProps} />;
    }
  };

  return (
    // Near-fullscreen dialog that grows with its content: the actions bar sits
    // right below the last row, and only past the viewport height the table
    // itself scrolls (the actions stay visible).
    <Dialog
      open
      fullWidth
      maxWidth={false}
      onClose={requestClose}
      PaperProps={{ sx: { m: 2, width: 'calc(100% - 32px)', maxHeight: 'calc(100% - 32px)' } }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        Quick edit: {resource.replaceAll('_', ' ')}
        <Box sx={{ flex: 1 }} />
        <Button size="small" startIcon={<CopyIcon />} onClick={copyGrid} disabled={saving}>
          Copy
        </Button>
        <Button size="small" startIcon={<PasteIcon />} onClick={() => requestPaste(false)} disabled={saving}>
          Paste
        </Button>
        <Tooltip title="Choose the rows and columns Copy and Paste work on">
          <Button
            size="small"
            startIcon={<SelectIcon />}
            variant={selectMode ? 'contained' : 'text'}
            onClick={toggleSelectMode}
            disabled={saving}
          >
            Select
          </Button>
        </Tooltip>
      </DialogTitle>
      {/* overflow hidden + minHeight 0 keep the scrolling inside the table
          container, so the actions bar stays visible (Firefox included). */}
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {rows.some((row) => row.serverError) && (
          <Alert severity="warning" sx={{ mb: 1 }}>
            Some rows could not be saved — hover the row icons for details.
          </Alert>
        )}
        <TableContainer sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: selectMode ? 140 : 110, whiteSpace: 'nowrap' }}>
                  {selectMode && (
                    <>
                      <Tooltip title="All rows">
                        <Checkbox size="small" sx={{ p: 0, mr: 1 }}
                          checked={selectedRowCount === rows.length}
                          indeterminate={selectedRowCount > 0 && selectedRowCount < rows.length}
                          onChange={toggleAllRows} />
                      </Tooltip>
                      <Tooltip title="All columns">
                        <Checkbox size="small" sx={{ p: 0 }}
                          checked={selectedColCount === allColNames().length}
                          indeterminate={selectedColCount > 0 && selectedColCount < allColNames().length}
                          onChange={toggleAllCols} />
                      </Tooltip>
                    </>
                  )}
                </TableCell>
                {showIdColumn && (
                  <TableCell>
                    {selectMode && (
                      <Checkbox size="small" sx={{ p: 0, mr: 0.5 }}
                        checked={selectedColNames.has(ID_COLUMN)}
                        onChange={() => toggleSelectedCol(ID_COLUMN)} />
                    )}
                    Id
                  </TableCell>
                )}
                {tableFields.map((field) => (
                  <TableCell key={field.name} sx={{ minWidth: columnMinWidth(field), py: 0.5 }}>
                    {selectMode && (
                      <Checkbox size="small" sx={{ p: 0, mr: 0.5 }}
                        checked={selectedColNames.has(field.name)}
                        onChange={() => toggleSelectedCol(field.name)} />
                    )}
                    {columnLabel(field)}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key} hover sx={row.deleted ? { opacity: 0.5 } : undefined}>
                  <TableCell sx={{ whiteSpace: 'nowrap', py: 0.25 }}>
                    {selectMode && (
                      <Checkbox size="small" sx={{ p: 0, mr: 0.5 }}
                        checked={selectedRowKeys.has(row.key)}
                        onChange={() => toggleSelectedRow(row.key)} />
                    )}
                    {rowStatus(row)}
                    {rowActions(row)}
                  </TableCell>
                  {showIdColumn && (
                    <TableCell sx={{ py: 0.25 }}>
                      <Typography variant="body2" color="text.secondary" noWrap
                        sx={row.deleted ? { textDecoration: 'line-through' } : undefined}>
                        {row.record ? row.record.id_presentation : '(new)'}
                      </Typography>
                    </TableCell>
                  )}
                  {tableFields.map((field) => (
                    <TableCell key={field.name} sx={{ verticalAlign: 'middle', py: 0.25 }}>
                      {renderCell(row, field)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>
      <DialogActions>
        {config.canCreate && (
          <Button startIcon={<AddRowIcon />} onClick={addRow} disabled={saving}>
            Add row
          </Button>
        )}
        {config.canCreate && (
          <Tooltip title="Insert the clipboard rows as new rows">
            <Button startIcon={<PasteInsertIcon />} onClick={() => requestPaste(true)} disabled={saving}>
              Paste insert
            </Button>
          </Tooltip>
        )}
        <Box sx={{ flex: 1 }} />
        <Button onClick={requestClose} disabled={saving}>Close</Button>
        <Button
          variant="contained"
          onClick={saveAll}
          disabled={saving || !rows.some(isDirty)}
        >
          Save all
        </Button>
      </DialogActions>
      <Dialog open={confirmDiscard} onClose={() => setConfirmDiscard(false)}>
        <DialogTitle>Discard unsaved changes?</DialogTitle>
        <DialogActions>
          <Button onClick={() => setConfirmDiscard(false)}>Keep editing</Button>
          <Button color="error" onClick={onClose}>Discard</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={!!pasteCapture} onClose={() => setPasteCapture(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Paste from the clipboard</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            This browser does not allow reading the clipboard directly.
            Press Ctrl+V (Cmd+V on Mac) in the box below to paste.
          </Typography>
          <MuiTextField
            autoFocus
            fullWidth
            multiline
            rows={3}
            value=""
            placeholder="Press Ctrl+V here"
            onChange={() => {}}
            onPaste={(event) => {
              event.preventDefault();
              pasteSeq.current += 1; // invalidate any still-pending native read
              const text = event.clipboardData.getData('text/plain');
              const insert = pasteCapture.insert;
              setPasteCapture(null);
              applyPasteText(text, insert);
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPasteCapture(null)}>Cancel</Button>
        </DialogActions>
      </Dialog>
    </Dialog>
  );
};

export const QuickEditButton = () => {
  const { resource, data } = useListContext();
  const [open, setOpen] = React.useState(false);
  const config = QUICK_EDIT_CONFIG[resource];
  if (!config) return null;
  return (
    <>
      <Button size="small" startIcon={<QuickEditIcon />} onClick={() => setOpen(true)} disabled={!data}>
        Quick edit
      </Button>
      {open && (
        <QUICK_EDIT_DIALOG
          resource={resource}
          config={config}
          records={data}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
};

// Clears the persisted DatagridConfigurable column selection for this resource
// (or for an explicit preferenceKey when the datagrid uses a custom one).
export const RESET_COLUMNS_BUTTON = ({ preferenceKey }) => {
  const { resource } = useListContext();
  const removeItems = useRemoveItemsFromStore();
  const notify = useNotify();
  return (
    <Tooltip title="Reset the visible columns to the default">
      <Button
        size="small"
        startIcon={<ResetColumnsIcon />}
        onClick={() => {
          removeItems(`preferences.${preferenceKey ?? `${resource}.datagrid`}`);
          notify('Columns reset to default', { type: 'info' });
        }}
      >
        Reset columns
      </Button>
    </Tooltip>
  );
};
"""
