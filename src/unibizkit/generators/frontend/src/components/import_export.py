def generate(customization: bool) -> str:
    template = """import * as React from 'react';
import {
  CreateButton, FilterButton, SelectColumnsButton, TopToolbar, downloadCSV,
  useDataProvider, useListContext, useNotify, usePermissions,
  useRefresh, useResourceDefinition
} from 'react-admin';
import { QuickEditButton, RESET_COLUMNS_BUTTON } from './quick_edit';
__CUSTOM_IMPORT__
import Papa from 'papaparse';
import {
  Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, FormGroup, LinearProgress,
  Table, TableBody, TableCell, TableHead, TableRow, Typography
} from '@mui/material';
import {
  CloudDownload as CloudDownloadIcon,
  CloudUpload as CloudUploadIcon
} from '@mui/icons-material';
import { supabaseClient } from '../supabaseClient';
import { IMPORT_EXPORT_CONFIG } from '../importExportConfig';

// CSV format: the row key is `id_presentation` (empty = insert, non-empty = update).
// Scalar columns are field names; FK and m:n cells carry the target's id_presentation
// (m:n values joined with newlines inside the quoted cell); document columns are
// `doc:<tag>:filename` + `doc:<tag>:content` (base64 data URI, 1 MB decoded limit).
const M2M_SEPARATOR = '\\n';
const DOC_SIZE_LIMIT = 1000000;
const PAGE_SIZE = 1000;    // rows per getList page while exporting
const LOOKUP_CHUNK = 100;  // values per .in() lookup, bounded by URL length
const INSERT_CHUNK = 100;  // rows per bulk insert
const PARALLEL_OPS = 5;    // concurrent updates / storage transfers

const chunked = (items, size) => {
  const chunks = [];
  for (let i = 0; i < items.length; i += size) chunks.push(items.slice(i, i + size));
  return chunks;
};

export const mapWithConcurrency = async (items, limit, fn) => {
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) await fn(items[next++]);
  });
  await Promise.all(workers);
};

const blobToDataUri = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = reject;
  reader.readAsDataURL(blob);
});

// Accepts a full data URI (as exported) or bare base64.
const dataUriToBlob = (value) => {
  const match = value.match(/^data:([^;,]*);base64,(.*)$/s);
  const base64 = match ? match[2] : value;
  const binary = atob(base64.replace(/\\s/g, ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], match && match[1] ? { type: match[1] } : undefined);
};

const parseCsvFile = (file) => new Promise((resolve, reject) => {
  Papa.parse(file, { header: true, skipEmptyLines: 'greedy', complete: resolve, error: reject });
});

// Map id -> id_presentation for the given record ids.
const fetchPresentationsByIds = async (table, ids) => {
  const map = new Map();
  for (const chunk of chunked([...new Set(ids)], LOOKUP_CHUNK)) {
    const { data, error } = await supabaseClient
      .from(table).select('"id","id_presentation"').in('"id"', chunk);
    if (error) throw new Error(`${table}: ${error.message}`);
    (data || []).forEach(r => map.set(r.id, r.id_presentation));
  }
  return map;
};

// Map id_presentation -> [ids]; more than one id means the value is ambiguous.
// PostgREST trims unquoted in.() items (and needs quotes around commas/parens),
// while postgrest-js .in() only auto-quotes for commas/parens — so the filter is
// built through .or() with every value explicitly double-quoted and escaped.
const fetchIdsByPresentation = async (table, values) => {
  const map = new Map();
  for (const chunk of chunked([...new Set(values)], LOOKUP_CHUNK)) {
    const quoted = chunk.map(v => `"${v.replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"')}"`);
    const { data, error } = await supabaseClient
      .from(table).select('"id","id_presentation"')
      .or(`id_presentation.in.(${quoted.join(',')})`);
    if (error) throw new Error(`${table}: ${error.message}`);
    (data || []).forEach(r => {
      if (!map.has(r.id_presentation)) map.set(r.id_presentation, []);
      map.get(r.id_presentation).push(r.id);
    });
  }
  return map;
};

// Presentation values are matched both verbatim and trimmed: exported labels can
// legitimately carry surrounding whitespace (e.g. a null parent in a recursive
// label), while hand-edited cells often gain stray spaces.
const addLookupValue = (set, value) => { set.add(value); set.add(value.trim()); };
const lookupIds = (map, value) => map.get(value) ?? map.get(value.trim());

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

const formatCell = (value, field, fkMaps) => {
  if (value === null || value === undefined) return '';
  if (field.type === 'relation_to_one') return fkMaps[field.name].get(value) ?? '';
  if (field.type === 'boolean') return value ? 'true' : 'false';
  return String(value);
};

const runExport = async (dataProvider, resource, config, filterValues, sort, selection, setStatus) => {
  const warnings = [];

  setStatus({ label: 'Fetching records…', value: null });
  const rows = [];
  for (let page = 1; ; page++) {
    const { data } = await dataProvider.getList(resource, {
      pagination: { page, perPage: PAGE_SIZE },
      sort: sort || { field: 'id', order: 'ASC' },
      filter: filterValues || {},
    });
    rows.push(...data);
    setStatus({ label: `Fetching records… (${rows.length})`, value: null });
    if (data.length < PAGE_SIZE) break;
  }
  const rowIds = rows.map(r => r.id);

  const selectedFields = config.fields.filter(f => selection.fields[f.name]);
  const selectedM2m = Object.keys(config.m2m).filter(name => selection.m2m[name]);
  const selectedTags = config.documents ? config.documents.tags.filter(t => selection.tags[t]) : [];

  setStatus({ label: 'Resolving references…', value: null });
  const fkMaps = {};
  for (const field of selectedFields.filter(f => f.type === 'relation_to_one')) {
    const ids = rows.map(r => r[field.name]).filter(v => v !== null && v !== undefined);
    fkMaps[field.name] = await fetchPresentationsByIds(field.target, ids);
  }

  const m2mValues = {};
  for (const name of selectedM2m) {
    const link = config.m2m[name];
    const pairs = [];
    for (const chunk of chunked(rowIds, LOOKUP_CHUNK)) {
      const { data, error } = await supabaseClient
        .from(link.resource)
        .select(`"${link.linkField}","${link.targetField}"`)
        .in(`"${link.linkField}"`, chunk);
      if (error) throw new Error(`${link.resource}: ${error.message}`);
      pairs.push(...(data || []));
    }
    const targetMap = await fetchPresentationsByIds(link.target, pairs.map(p => p[link.targetField]));
    m2mValues[name] = new Map();
    pairs.forEach(p => {
      const rowId = p[link.linkField];
      if (!m2mValues[name].has(rowId)) m2mValues[name].set(rowId, []);
      m2mValues[name].get(rowId).push(targetMap.get(p[link.targetField]) ?? '');
    });
  }

  const docValues = new Map();
  if (selectedTags.length > 0) {
    const docsConfig = config.documents;
    const docs = [];
    for (const chunk of chunked(rowIds, LOOKUP_CHUNK)) {
      let query = supabaseClient.from(docsConfig.table)
        .select('*')
        .in(`"${docsConfig.fkCol}"`, chunk)
        .in('"tag"', selectedTags);
      if (docsConfig.versioned) query = query.eq('"is_current"', true);
      const { data, error } = await query;
      if (error) throw new Error(`${docsConfig.table}: ${error.message}`);
      docs.push(...(data || []));
    }
    let done = 0;
    await mapWithConcurrency(docs, PARALLEL_OPS, async (doc) => {
      const { data: blob, error } = await supabaseClient.storage
        .from(docsConfig.bucket).download(doc.storage_path);
      done++;
      setStatus({ label: `Downloading documents… (${done}/${docs.length})`, value: Math.round(done * 100 / docs.length) });
      const filename = doc.storage_path.split('/').pop();
      if (error) {
        warnings.push(`document ${doc.storage_path}: download failed (${error.message})`);
        return;
      }
      if (blob.size > DOC_SIZE_LIMIT) {
        warnings.push(`document ${filename} (tag ${doc.tag}): ${(blob.size / 1000000).toFixed(1)} MB exceeds the 1 MB limit — skipped`);
        return;
      }
      const rowId = doc[docsConfig.fkCol];
      if (!docValues.has(rowId)) docValues.set(rowId, {});
      docValues.get(rowId)[doc.tag] = { filename, content: await blobToDataUri(blob) };
    });
  }

  setStatus({ label: 'Building CSV…', value: null });
  const headers = [
    'id_presentation',
    ...selectedFields.map(f => f.name),
    ...selectedM2m,
    ...selectedTags.flatMap(tag => [`doc:${tag}:filename`, `doc:${tag}:content`]),
  ];
  const data = rows.map(row => {
    const out = [row.id_presentation ?? ''];
    for (const field of selectedFields) out.push(formatCell(row[field.name], field, fkMaps));
    for (const name of selectedM2m) out.push((m2mValues[name].get(row.id) || []).join(M2M_SEPARATOR));
    for (const tag of selectedTags) {
      const doc = (docValues.get(row.id) || {})[tag];
      out.push(doc ? doc.filename : '', doc ? doc.content : '');
    }
    return out;
  });
  return { csv: Papa.unparse({ fields: headers, data }), rowCount: rows.length, warnings };
};

// ---------------------------------------------------------------------------
// Import: validation
// ---------------------------------------------------------------------------

const parseScalar = (raw, field) => {
  const isText = field.type === 'string' || field.type === 'markdown';
  const v = isText ? raw : raw.trim();
  if (v === '') return { value: null };
  switch (field.type) {
    case 'integer':
      return /^-?\\d+$/.test(v) ? { value: parseInt(v, 10) } : { error: 'not an integer' };
    case 'decimal':
      return /^-?\\d+(\\.\\d+)?$/.test(v) ? { value: parseFloat(v) } : { error: 'not a number (use . as decimal separator)' };
    case 'boolean': {
      const s = v.toLowerCase();
      if (['true', '1', 'yes'].includes(s)) return { value: true };
      if (['false', '0', 'no'].includes(s)) return { value: false };
      return { error: 'not a boolean (true/false)' };
    }
    case 'date':
      return /^\\d{4}-\\d{2}-\\d{2}$/.test(v) ? { value: v } : { error: 'not a date (YYYY-MM-DD)' };
    case 'datetime':
      return isNaN(Date.parse(v)) ? { error: 'not a valid datetime (ISO 8601)' } : { value: v };
    case 'enum':
      return field.values.includes(v) ? { value: v } : { error: `not one of: ${field.values.join(', ')}` };
    default:
      return { value: v };
  }
};

// Parses the file and collects ALL problems before anything is written.
// Errors reference the CSV record number: header = line 1, first data row = 2
// (multiline cells make raw file line numbers ambiguous).
const parseAndValidate = async (resource, config, file) => {
  const errors = [];
  const addError = (row, column, message) => errors.push({ row, column, message });

  const parsed = await parseCsvFile(file);
  (parsed.errors || []).forEach(e =>
    addError(e.row !== undefined ? e.row + 2 : 1, '', e.message));

  const headers = parsed.meta.fields || [];
  const fieldByName = Object.fromEntries(config.fields.map(f => [f.name, f]));
  const docTags = config.documents ? config.documents.tags : [];
  const knownHeaders = new Set([
    'id_presentation',
    ...config.fields.map(f => f.name),
    ...Object.keys(config.m2m),
    ...docTags.flatMap(tag => [`doc:${tag}:filename`, `doc:${tag}:content`]),
  ]);
  headers.forEach(h => { if (!knownHeaders.has(h)) addError(1, h, 'unknown column'); });

  const hasKey = headers.includes('id_presentation');
  const fieldCols = headers.filter(h => fieldByName[h]);
  const m2mCols = headers.filter(h => config.m2m[h]);
  const docCols = docTags.filter(tag =>
    headers.includes(`doc:${tag}:filename`) || headers.includes(`doc:${tag}:content`));
  const fkCols = fieldCols.filter(c => fieldByName[c].type === 'relation_to_one');

  const keyCounts = new Map();
  const keySet = new Set();
  const fkValues = Object.fromEntries(fkCols.map(c => [c, new Set()]));
  const m2mTokens = Object.fromEntries(m2mCols.map(c => [c, new Set()]));

  const plans = parsed.data.map((record, idx) => {
    const row = idx + 2;
    const plan = { row, data: {}, raw: {}, m2m: {}, docs: [] };
    const rawKey = hasKey ? String(record.id_presentation ?? '') : '';
    plan.key = rawKey.trim() === '' ? '' : rawKey;
    plan.action = plan.key ? 'update' : 'insert';
    if (plan.key) {
      keyCounts.set(plan.key.trim(), (keyCounts.get(plan.key.trim()) || 0) + 1);
      addLookupValue(keySet, plan.key);
    }

    for (const col of fieldCols) {
      const field = fieldByName[col];
      const raw = String(record[col] ?? '');
      if (field.type === 'relation_to_one') {
        plan.raw[col] = raw;
        if (raw.trim() === '') plan.data[col] = null;
        else addLookupValue(fkValues[col], raw);
        if (field.required && raw.trim() === '') addError(row, col, 'required value is empty');
        continue;
      }
      const { value, error } = parseScalar(raw, field);
      if (error) {
        addError(row, col, error);
        continue;
      }
      plan.data[col] = value;
      if (field.required && value === null) addError(row, col, 'required value is empty');
    }

    for (const col of m2mCols) {
      const tokens = String(record[col] ?? '')
        .split(/\\r?\\n/).filter(t => t.trim() !== '');
      plan.raw[col] = tokens;
      tokens.forEach(t => addLookupValue(m2mTokens[col], t));
    }

    for (const tag of docCols) {
      const filename = String(record[`doc:${tag}:filename`] ?? '').trim();
      const content = String(record[`doc:${tag}:content`] ?? '').trim();
      if (!filename && !content) continue;
      if (!filename) {
        addError(row, `doc:${tag}:filename`, 'content given without a filename');
        continue;
      }
      if (!content) {
        addError(row, `doc:${tag}:content`, 'filename given without content');
        continue;
      }
      try {
        const blob = dataUriToBlob(content);
        if (blob.size > DOC_SIZE_LIMIT) {
          addError(row, `doc:${tag}:content`, `decoded size ${(blob.size / 1000000).toFixed(1)} MB exceeds the 1 MB limit`);
        } else {
          plan.docs.push({ tag, filename, blob });
        }
      } catch (err) {
        addError(row, `doc:${tag}:content`, 'invalid base64 content');
      }
    }
    return plan;
  });

  const inserts = plans.filter(p => p.action === 'insert');
  if (inserts.length > 0) {
    config.fields
      .filter(f => f.required && !fieldCols.includes(f.name))
      .forEach(f => addError(1, f.name, 'required column missing (needed to insert new records)'));
  }

  const keyMap = keySet.size ? await fetchIdsByPresentation(resource, [...keySet]) : new Map();
  const fkMaps = {};
  for (const col of fkCols) {
    fkMaps[col] = fkValues[col].size
      ? await fetchIdsByPresentation(fieldByName[col].target, [...fkValues[col]]) : new Map();
  }
  const m2mMaps = {};
  for (const col of m2mCols) {
    m2mMaps[col] = m2mTokens[col].size
      ? await fetchIdsByPresentation(config.m2m[col].target, [...m2mTokens[col]]) : new Map();
  }

  for (const plan of plans) {
    if (plan.action === 'update') {
      if (keyCounts.get(plan.key.trim()) > 1) {
        addError(plan.row, 'id_presentation', `"${plan.key}" appears ${keyCounts.get(plan.key.trim())} times in the file`);
      }
      const ids = lookupIds(keyMap, plan.key);
      if (!ids) addError(plan.row, 'id_presentation', `"${plan.key}" not found — cannot update`);
      else if (ids.length > 1) addError(plan.row, 'id_presentation', `"${plan.key}" is ambiguous (${ids.length} matches)`);
      else plan.id = ids[0];
    }
    for (const col of fkCols) {
      const v = plan.raw[col];
      if (!v || v.trim() === '') continue;
      const ids = lookupIds(fkMaps[col], v);
      if (!ids) addError(plan.row, col, `${fieldByName[col].target} "${v}" not found`);
      else if (ids.length > 1) addError(plan.row, col, `${fieldByName[col].target} "${v}" is ambiguous (${ids.length} matches)`);
      else plan.data[col] = ids[0];
    }
    for (const col of m2mCols) {
      plan.m2m[col] = [];
      for (const token of plan.raw[col]) {
        const ids = lookupIds(m2mMaps[col], token);
        if (!ids) addError(plan.row, col, `${config.m2m[col].target} "${token}" not found`);
        else if (ids.length > 1) addError(plan.row, col, `${config.m2m[col].target} "${token}" is ambiguous (${ids.length} matches)`);
        else plan.m2m[col].push(ids[0]);
      }
    }
  }

  errors.sort((a, b) => a.row - b.row);
  return {
    errors, plans, fieldCols, m2mCols,
    counts: { inserts: inserts.length, updates: plans.length - inserts.length },
  };
};

// ---------------------------------------------------------------------------
// Import: execution
// ---------------------------------------------------------------------------

const executeImport = async (resource, config, validated, setStatus) => {
  const { plans, fieldCols, m2mCols } = validated;
  const failures = [];
  const inserts = plans.filter(p => p.action === 'insert');
  const updates = plans.filter(p => p.action === 'update');
  const docCount = plans.reduce((n, p) => n + p.docs.length, 0);
  const totalUnits = inserts.length + updates.length
    + (m2mCols.length ? plans.length : 0) + docCount;
  let done = 0;
  const tick = (label, units) => {
    done += units;
    setStatus({ label, value: totalUnits ? Math.round(done * 100 / totalUnits) : 100 });
  };

  // PostgREST bulk insert requires every record to have the same keys, so each
  // record carries all CSV field columns, with null for empty cells.
  const recordFor = (plan) => Object.fromEntries(fieldCols.map(col => [col, plan.data[col] ?? null]));

  for (const chunk of chunked(inserts, INSERT_CHUNK)) {
    const { data, error } = await supabaseClient
      .from(resource).insert(chunk.map(recordFor)).select('"id"');
    if (error || !data || data.length !== chunk.length) {
      chunk.forEach(p => {
        p.failed = true;
        failures.push({ row: p.row, message: error ? error.message : 'insert failed' });
      });
    } else {
      data.forEach((r, i) => { chunk[i].id = r.id; });
    }
    tick('Inserting records…', chunk.length);
  }

  for (const chunk of chunked(updates, PARALLEL_OPS)) {
    await Promise.all(chunk.map(async (p) => {
      if (fieldCols.length === 0) return;
      const { error } = await supabaseClient
        .from(resource).update(recordFor(p)).eq('"id"', p.id);
      if (error) {
        p.failed = true;
        failures.push({ row: p.row, message: error.message });
      }
    }));
    tick('Updating records…', chunk.length);
  }

  if (m2mCols.length) {
    for (const chunk of chunked(plans, PARALLEL_OPS)) {
      await Promise.all(chunk.map(async (p) => {
        if (p.failed) return;
        for (const col of m2mCols) {
          const link = config.m2m[col];
          try {
            // Same replace semantics as the data provider: drop all links, re-insert.
            if (p.action === 'update') {
              const { error } = await supabaseClient
                .from(link.resource).delete().eq(`"${link.linkField}"`, p.id);
              if (error) throw error;
            }
            if (p.m2m[col].length) {
              const rows = p.m2m[col].map(targetId => ({
                [link.linkField]: p.id,
                [link.targetField]: targetId,
              }));
              const { error } = await supabaseClient.from(link.resource).insert(rows);
              if (error) throw error;
            }
          } catch (err) {
            failures.push({ row: p.row, message: `${col}: ${err.message}` });
          }
        }
      }));
      tick('Updating relations…', chunk.length);
    }
  }

  const docOps = plans.filter(p => !p.failed)
    .flatMap(p => p.docs.map(doc => ({ ...doc, plan: p })));
  await mapWithConcurrency(docOps, PARALLEL_OPS, async (op) => {
    const d = config.documents;
    try {
      // Uploads only touch Storage; DB triggers keep the document table in sync.
      if (d.versioned) {
        const { data: existing } = await supabaseClient.from(d.table)
          .select('"version"')
          .eq(`"${d.fkCol}"`, op.plan.id).eq('"tag"', op.tag)
          .order('"version"', { ascending: false }).limit(1);
        const version = existing?.length ? existing[0].version + 1 : 1;
        const { error } = await supabaseClient.storage.from(d.bucket)
          .upload(`${op.plan.id}/${op.tag}/v${version}/${op.filename}`, op.blob);
        if (error) throw error;
      } else {
        const { error } = await supabaseClient.storage.from(d.bucket)
          .upload(`${op.plan.id}/${op.tag}/${op.filename}`, op.blob, { upsert: true });
        if (error) throw error;
      }
    } catch (err) {
      failures.push({ row: op.plan.row, message: `doc ${op.tag}: ${err.message}` });
    }
    tick('Uploading documents…', 1);
  });

  failures.sort((a, b) => a.row - b.row);
  return { failures, total: plans.length };
};

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

const CheckboxGroup = ({ title, names, checked, onChange }) => {
  if (!names.length) return null;
  return (
    <Box sx={{ mb: 1 }}>
      <Typography variant="subtitle2">{title}</Typography>
      <FormGroup row>
        {names.map(name => (
          <FormControlLabel
            key={name}
            control={<Checkbox size="small" checked={!!checked[name]} onChange={e => onChange(name, e.target.checked)} />}
            label={name}
          />
        ))}
      </FormGroup>
    </Box>
  );
};

const ProblemTable = ({ problems }) => (
  <Box sx={{ maxHeight: 300, overflow: 'auto' }}>
    <Table size="small" stickyHeader>
      <TableHead>
        <TableRow>
          <TableCell>Row</TableCell>
          <TableCell>Column</TableCell>
          <TableCell>Problem</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {problems.map((p, i) => (
          <TableRow key={i}>
            <TableCell>{p.row}</TableCell>
            <TableCell>{p.column || ''}</TableCell>
            <TableCell>{p.message}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </Box>
);

const ExportDialogButton = ({ resource, config, filterValues, sort, canReadDocs }) => {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const [open, setOpen] = React.useState(false);
  const [selection, setSelection] = React.useState(null);
  const [status, setStatus] = React.useState(null);
  const [warnings, setWarnings] = React.useState([]);

  const docTags = (config.documents && canReadDocs) ? config.documents.tags : [];

  const openDialog = () => {
    setSelection({
      fields: Object.fromEntries(config.fields.map(f => [f.name, true])),
      m2m: Object.fromEntries(Object.keys(config.m2m).map(name => [name, true])),
      tags: Object.fromEntries(docTags.map(tag => [tag, false])),
    });
    setStatus(null);
    setWarnings([]);
    setOpen(true);
  };

  const toggle = (group) => (name, value) =>
    setSelection(prev => ({ ...prev, [group]: { ...prev[group], [name]: value } }));

  const handleExport = async () => {
    try {
      const { csv, rowCount, warnings: w } = await runExport(
        dataProvider, resource, config, filterValues, sort, selection, setStatus);
      downloadCSV(csv, `${resource}_${new Date().toISOString().slice(0, 10)}`);
      setStatus(null);
      notify(`Exported ${rowCount} records`, { type: 'info' });
      if (w.length) setWarnings(w);
      else setOpen(false);
    } catch (err) {
      setStatus(null);
      notify(`Export failed: ${err.message}`, { type: 'error' });
    }
  };

  return (
    <>
      <Button size="small" startIcon={<CloudDownloadIcon />} onClick={openDialog}>Export</Button>
      <Dialog open={open} onClose={() => !status && setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Export {resource} to CSV</DialogTitle>
        <DialogContent>
          {selection && !status && !warnings.length && (
            <>
              <FormControlLabel control={<Checkbox size="small" checked disabled />} label="id_presentation (key)" />
              <CheckboxGroup title="Fields" names={config.fields.map(f => f.name)}
                checked={selection.fields} onChange={toggle('fields')} />
              <CheckboxGroup title="Relations" names={Object.keys(config.m2m)}
                checked={selection.m2m} onChange={toggle('m2m')} />
              <CheckboxGroup title="Documents (base64, max 1 MB per file)" names={docTags}
                checked={selection.tags} onChange={toggle('tags')} />
            </>
          )}
          {status && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2">{status.label}</Typography>
              <LinearProgress sx={{ mt: 1 }}
                variant={status.value === null ? 'indeterminate' : 'determinate'}
                value={status.value ?? 0} />
            </Box>
          )}
          {warnings.length > 0 && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                Exported with warnings:
              </Typography>
              {warnings.map((w, i) => <Typography key={i} variant="body2">{w}</Typography>)}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} disabled={!!status}>Close</Button>
          {!warnings.length && (
            <Button variant="contained" onClick={handleExport} disabled={!!status}>Export</Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
};

const ImportDialogButton = ({ resource, config }) => {
  const notify = useNotify();
  const refresh = useRefresh();
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState('pick'); // pick|validating|errors|confirm|running|done
  const [errors, setErrors] = React.useState([]);
  const [validated, setValidated] = React.useState(null);
  const [status, setStatus] = React.useState(null);
  const [result, setResult] = React.useState(null);

  const openDialog = () => { setStep('pick'); setErrors([]); setValidated(null); setResult(null); setOpen(true); };
  const busy = step === 'validating' || step === 'running';

  const handleFile = async (file) => {
    if (!file) return;
    setStep('validating');
    try {
      const v = await parseAndValidate(resource, config, file);
      if (v.errors.length) {
        setErrors(v.errors);
        setStep('errors');
      } else if (!v.plans.length) {
        notify('The file contains no data rows', { type: 'warning' });
        setStep('pick');
      } else {
        setValidated(v);
        setStep('confirm');
      }
    } catch (err) {
      notify(`Import failed: ${err.message}`, { type: 'error' });
      setStep('pick');
    }
  };

  const handleConfirm = async () => {
    setStep('running');
    const res = await executeImport(resource, config, validated, setStatus);
    setResult(res);
    setStep('done');
    refresh();
  };

  return (
    <>
      <Button size="small" startIcon={<CloudUploadIcon />} onClick={openDialog}>Import</Button>
      <Dialog open={open} onClose={() => !busy && setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Import {resource} from CSV</DialogTitle>
        <DialogContent>
          {step === 'pick' && (
            <>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Rows with an empty <code>id_presentation</code> are inserted; rows with a value
                update the matching record. Only the columns present in the file are written.
              </Typography>
              <Button component="label" variant="outlined" startIcon={<CloudUploadIcon />}>
                Choose CSV file
                <input type="file" hidden accept=".csv,text/csv"
                  onChange={e => { handleFile(e.target.files[0]); e.target.value = ''; }} />
              </Button>
            </>
          )}
          {step === 'validating' && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2">Validating file…</Typography>
              <LinearProgress sx={{ mt: 1 }} />
            </Box>
          )}
          {step === 'errors' && (
            <>
              <Alert severity="error" sx={{ mb: 1 }}>
                {errors.length} problem{errors.length === 1 ? '' : 's'} found — nothing was imported.
                Fix the file and try again.
              </Alert>
              <ProblemTable problems={errors} />
            </>
          )}
          {step === 'confirm' && validated && (
            <Alert severity="info">
              This will perform {validated.counts.inserts} inserts, {validated.counts.updates} updates. Continue?
            </Alert>
          )}
          {step === 'running' && status && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2">{status.label}</Typography>
              <LinearProgress sx={{ mt: 1 }} variant="determinate" value={status.value ?? 0} />
            </Box>
          )}
          {step === 'done' && result && (
            <>
              <Alert severity={result.failures.length ? 'warning' : 'success'} sx={{ mb: 1 }}>
                {result.total - new Set(result.failures.map(f => f.row)).size} of {result.total} rows
                imported{result.failures.length ? `, ${result.failures.length} problems` : ' successfully'}.
              </Alert>
              {result.failures.length > 0 && <ProblemTable problems={result.failures} />}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} disabled={busy}>Close</Button>
          {step === 'confirm' && (
            <Button variant="contained" onClick={handleConfirm}>Confirm</Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
};

export const ImportExportActions = () => {
  const { resource, filterValues, sort } = useListContext();
  const { hasCreate } = useResourceDefinition();
  const { permissions } = usePermissions();
__CUSTOM_PREF__  const config = IMPORT_EXPORT_CONFIG[resource];
  const canWrite = permissions?.[resource]?.includes('write')
    || permissions?.['*']?.includes('write');
  const canEdit = canWrite || permissions?.[resource]?.includes('edit');
  const canReadDocs = permissions?.[`${resource}._documents`]?.includes('read')
    || permissions?.[`${resource}._documents`]?.includes('write')
    || permissions?.['*']?.includes('read')
    || permissions?.['*']?.includes('write');
  return (
    <TopToolbar>
__DESIGN_BADGE__      <FilterButton />
      <SelectColumnsButton__PREF_PROP__ />
      <RESET_COLUMNS_BUTTON__PREF_PROP__ />
      {hasCreate && <CreateButton />}
      {canEdit && <QuickEditButton />}
      {config && (
        <ExportDialogButton resource={resource} config={config}
          filterValues={filterValues} sort={sort} canReadDocs={canReadDocs} />
      )}
      {config && canWrite && <ImportDialogButton resource={resource} config={config} />}
    </TopToolbar>
  );
};
"""

    if customization:
        custom_import = "import { useCustomization, DesignBadge } from './customization';\n"
        custom_pref = (
            "  const custom = useCustomization();\n"
            "  // Customized column sets live in their own preference bucket (see\n"
            "  // customizationConfig.js); the column selector and reset buttons must target\n"
            "  // the same key as the DatagridConfigurable of this list.\n"
            "  const listCfg = custom && custom.lists[resource];\n"
            "  const preferenceKey = listCfg ? listCfg.prefKey : undefined;\n"
        )
        design_badge = "      <DesignBadge target={{ kind: 'list', concept: resource }} />\n"
        pref_prop = " preferenceKey={preferenceKey}"
    else:
        custom_import = ""
        custom_pref = ""
        design_badge = ""
        pref_prop = ""
    return (
        template
        .replace("__CUSTOM_IMPORT__\n", custom_import)
        .replace("__CUSTOM_PREF__", custom_pref)
        .replace("__DESIGN_BADGE__", design_badge)
        .replace("__PREF_PROP__", pref_prop)
    )
