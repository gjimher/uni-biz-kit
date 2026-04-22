def generate() -> str:
    return """import * as React from 'react';
import { useRecordContext, useNotify, usePermissions } from 'react-admin';
import { supabaseClient } from '../supabaseClient';
import {
  Box, Button, Chip, CircularProgress, Collapse, IconButton,
  Table, TableBody, TableCell, TableHead, TableRow, Typography
} from '@mui/material';
import {
  CloudUpload as CloudUploadIcon,
  CloudDownload as CloudDownloadIcon,
  Delete as DeleteIcon,
  History as HistoryIcon,
  Restore as RestoreIcon
} from '@mui/icons-material';

export const DocumentTab = ({ conceptName, tags, versioned, canEditParent = true }) => {
  const record = useRecordContext();
  const { permissions } = usePermissions();
  const notify = useNotify();

  const tableName = `${conceptName}_document`;
  const fkCol = `${conceptName}_id`;
  const bucketName = `${conceptName}-documents`;

  const hasDocPermission = permissions?.[`${conceptName}._documents`]?.includes('write')
    || permissions?.[`${conceptName}._documents`]?.includes('read')
    || permissions?.['*']?.includes('write')
    || permissions?.['*']?.includes('read');
  const canWrite = (permissions?.[`${conceptName}._documents`]?.includes('write')
    || permissions?.['*']?.includes('write')) && canEditParent;
  const canRead = hasDocPermission;

  const [docs, setDocs] = React.useState([]);
  const [uploading, setUploading] = React.useState({});
  const [expandedTag, setExpandedTag] = React.useState(null);
  const [tagHistory, setTagHistory] = React.useState([]);
  const [loadingHistory, setLoadingHistory] = React.useState(false);

  const loadDocs = React.useCallback(async () => {
    if (!record?.id || !canRead) return;
    let query = supabaseClient
      .from(tableName)
      .select('*')
      .eq(`"${fkCol}"`, record.id);
    if (versioned) query = query.eq('"is_current"', true);
    const { data, error } = await query.order('"tag"');
    if (!error) setDocs(data || []);
  }, [record?.id, canRead, tableName, fkCol, versioned]);

  React.useEffect(() => { loadDocs(); }, [loadDocs]);

  const handleUpload = async (tag, file) => {
    if (!file) return;
    setUploading(prev => ({ ...prev, [tag]: true }));
    try {
      let version = 1;
      let storagePath;
      if (versioned) {
        const { data: existing } = await supabaseClient
          .from(tableName)
          .select('"version"')
          .eq(`"${fkCol}"`, record.id)
          .eq('"tag"', tag)
          .order('"version"', { ascending: false })
          .limit(1);
        if (existing?.length) version = existing[0].version + 1;
        storagePath = `${record.id}/${tag}/v${version}/${file.name}`;
      } else {
        storagePath = `${record.id}/${tag}/${file.name}`;
      }

      const { error: uploadError } = await supabaseClient.storage
        .from(bucketName)
        .upload(storagePath, file);
      if (uploadError) throw uploadError;

      if (versioned) {
        const { error: dbError } = await supabaseClient
          .from(tableName)
          .insert({ [fkCol]: record.id, tag, version, is_current: true, storage_path: storagePath });
        if (dbError) throw dbError;
      } else {
        const { error: dbError } = await supabaseClient
          .from(tableName)
          .upsert(
            { [fkCol]: record.id, tag, storage_path: storagePath },
            { onConflict: `${fkCol},tag` }
          );
        if (dbError) throw dbError;
      }

      notify('Document uploaded', { type: 'success' });
      await loadDocs();
      if (versioned && expandedTag === tag) await loadHistory(tag);
    } catch (err) {
      notify(`Upload failed: ${err.message}`, { type: 'error' });
    } finally {
      setUploading(prev => ({ ...prev, [tag]: false }));
    }
  };

  const handleDownload = async (storagePath) => {
    try {
      const { data, error } = await supabaseClient.storage
        .from(bucketName)
        .createSignedUrl(storagePath, 60);
      if (error) throw error;
      window.open(data.signedUrl, '_blank');
    } catch (err) {
      notify(`Download failed: ${err.message}`, { type: 'error' });
    }
  };

  const loadHistory = async (tag) => {
    setLoadingHistory(true);
    const { data } = await supabaseClient
      .from(tableName)
      .select('*')
      .eq(`"${fkCol}"`, record.id)
      .eq('"tag"', tag)
      .order('"version"', { ascending: false });
    setTagHistory(data || []);
    setLoadingHistory(false);
  };

  const handleToggleHistory = async (tag) => {
    if (expandedTag === tag) {
      setExpandedTag(null);
    } else {
      setExpandedTag(tag);
      await loadHistory(tag);
    }
  };

  const handleRestore = async (docId, tag) => {
    try {
      const { error } = await supabaseClient
        .from(tableName)
        .update({ is_current: true })
        .eq('"id"', docId);
      if (error) throw error;
      notify('Version restored', { type: 'success' });
      await loadDocs();
      await loadHistory(tag);
    } catch (err) {
      notify(`Restore failed: ${err.message}`, { type: 'error' });
    }
  };

  const handleDelete = async (docId, storagePath, tag, isCurrent) => {
    if (!window.confirm('Delete this document?')) return;
    try {
      await supabaseClient.storage.from(bucketName).remove([storagePath]);
      const { error } = await supabaseClient.from(tableName).delete().eq('"id"', docId);
      if (error) throw error;
      if (versioned && isCurrent) {
        const { data: next } = await supabaseClient
          .from(tableName)
          .select('id')
          .eq(`"${fkCol}"`, record.id)
          .eq('"tag"', tag)
          .order('"version"', { ascending: false })
          .limit(1);
        if (next?.length) {
          await supabaseClient.from(tableName).update({ is_current: true }).eq('"id"', next[0].id);
        }
      }
      notify('Document deleted', { type: 'success' });
      await loadDocs();
      if (versioned && expandedTag === tag) await loadHistory(tag);
    } catch (err) {
      notify(`Delete failed: ${err.message}`, { type: 'error' });
    }
  };

  if (!canRead) return null;

  return (
    <Box sx={{ width: '100%', mt: 1 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell><strong>Tag</strong></TableCell>
            {versioned && <TableCell><strong>Version</strong></TableCell>}
            <TableCell><strong>File</strong></TableCell>
            <TableCell align="right"><strong>Actions</strong></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {tags.map(tag => {
            const doc = docs.find(d => d.tag === tag);
            const isUploading = uploading[tag];
            const fileName = doc ? doc.storage_path.split('/').pop() : null;
            return (
              <React.Fragment key={tag}>
                <TableRow>
                  <TableCell><Chip label={tag} size="small" variant="outlined" /></TableCell>
                  {versioned && (
                    <TableCell>
                      {doc
                        ? `v${doc.version}`
                        : <Typography variant="caption" color="text.secondary">—</Typography>}
                    </TableCell>
                  )}
                  <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {fileName || <Typography variant="caption" color="text.secondary">No file</Typography>}
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end', alignItems: 'center' }}>
                      {doc && (
                        <IconButton size="small" onClick={() => handleDownload(doc.storage_path)} title="Download">
                          <CloudDownloadIcon fontSize="small" />
                        </IconButton>
                      )}
                      {versioned && doc && (
                        <IconButton
                          size="small"
                          onClick={() => handleToggleHistory(tag)}
                          title="Version history"
                          color={expandedTag === tag ? 'primary' : 'default'}
                        >
                          <HistoryIcon fontSize="small" />
                        </IconButton>
                      )}
                      {!versioned && canWrite && doc && (
                        <IconButton size="small" onClick={() => handleDelete(doc.id, doc.storage_path, tag, false)} title="Delete" color="error">
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      )}
                      {canWrite && (
                        <Button
                          component="label"
                          size="small"
                          variant="outlined"
                          disabled={isUploading}
                          startIcon={isUploading ? <CircularProgress size={14} /> : <CloudUploadIcon />}
                          sx={{ minWidth: 90 }}
                        >
                          {doc ? 'Replace' : 'Upload'}
                          <input type="file" hidden onChange={e => { handleUpload(tag, e.target.files[0]); e.target.value = ''; }} />
                        </Button>
                      )}
                    </Box>
                  </TableCell>
                </TableRow>
                {versioned && expandedTag === tag && (
                  <TableRow>
                    <TableCell colSpan={4} sx={{ py: 0, bgcolor: 'action.hover' }}>
                      <Collapse in={true} unmountOnExit>
                        <Box sx={{ p: 1 }}>
                          <Typography variant="caption" sx={{ fontWeight: 'bold', mb: 0.5, display: 'block' }}>
                            Version History
                          </Typography>
                          {loadingHistory ? <CircularProgress size={16} /> : (
                            <Table size="small">
                              <TableBody>
                                {tagHistory.map(h => (
                                  <TableRow key={h.id}>
                                    <TableCell sx={{ width: 60 }}>
                                      <Chip
                                        label={`v${h.version}`}
                                        size="small"
                                        color={h.is_current ? 'success' : 'default'}
                                        variant="outlined"
                                      />
                                    </TableCell>
                                    <TableCell sx={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                      {h.storage_path.split('/').pop()}
                                    </TableCell>
                                    <TableCell sx={{ width: 100, color: 'text.secondary', fontSize: '0.75rem' }}>
                                      {new Date(h._created_at).toLocaleDateString()}
                                    </TableCell>
                                    <TableCell align="right" sx={{ width: 80 }}>
                                      <IconButton size="small" onClick={() => handleDownload(h.storage_path)} title="Download">
                                        <CloudDownloadIcon fontSize="small" />
                                      </IconButton>
                                      {canWrite && !h.is_current && (
                                        <IconButton size="small" onClick={() => handleRestore(h.id, tag)} title="Restore this version">
                                          <RestoreIcon fontSize="small" />
                                        </IconButton>
                                      )}
                                      {canWrite && (
                                        <IconButton size="small" onClick={() => handleDelete(h.id, h.storage_path, tag, h.is_current)} title="Delete this version" color="error">
                                          <DeleteIcon fontSize="small" />
                                        </IconButton>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          )}
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
};
"""
