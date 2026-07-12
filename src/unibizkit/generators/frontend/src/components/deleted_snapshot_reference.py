def generate():
    return r'''import * as React from 'react';
import { ReferenceField, ReferenceInput, TextField, useRecordContext } from 'react-admin';
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Tooltip, Typography } from '@mui/material';

const formatSnapshotValue = (value) => {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
};

const DeletedSnapshotDialog = ({ snapshot, reference, open, onClose }) => {
    const displayValue = snapshot.id_presentation || `${reference} #${snapshot.id ?? '?'}`;
    return (
        <Dialog
            open={open}
            onClose={onClose}
            onClick={(event) => event.stopPropagation()}
            fullWidth
            maxWidth="sm"
        >
            <DialogTitle>{`Deleted: ${displayValue}`}</DialogTitle>
            <DialogContent dividers>
                {Object.entries(snapshot).map(([key, value]) => (
                    <Box key={key} sx={{ mb: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" display="block">
                            {key}
                        </Typography>
                        <Typography component="pre" variant="body2" sx={{ m: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                            {formatSnapshotValue(value)}
                        </Typography>
                    </Box>
                ))}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Close</Button>
            </DialogActions>
        </Dialog>
    );
};

const DeletedSnapshotIndicator = ({ snapshot, reference, showLabel = false }) => {
    const [open, setOpen] = React.useState(false);
    const displayValue = snapshot.id_presentation || `${reference} #${snapshot.id ?? '?'}`;

    return (
        <>
            {showLabel && (
                <Button
                    size="small"
                    onClick={(event) => {
                        event.stopPropagation();
                        setOpen(true);
                    }}
                    sx={{ textTransform: 'none', justifyContent: 'flex-start', padding: 0, minWidth: 0 }}
                >
                    {displayValue}
                </Button>
            )}
            <Tooltip title={`Deleted: ${displayValue}`}>
                <IconButton
                    size="small"
                    color="error"
                    aria-label={`Deleted: ${displayValue}`}
                    onClick={(event) => {
                        event.stopPropagation();
                        setOpen(true);
                    }}
                    sx={{ width: 24, height: 24, fontWeight: 700, fontSize: '0.75rem' }}
                >
                    D
                </IconButton>
            </Tooltip>
            <DeletedSnapshotDialog
                snapshot={snapshot}
                reference={reference}
                open={open}
                onClose={() => setOpen(false)}
            />
        </>
    );
};

export const DeletedSnapshotReference = ({ source, reference, snapshotSource, label }) => {
    const record = useRecordContext();

    if (!record) return null;

    if (record[source] !== null && record[source] !== undefined) {
        return (
            <ReferenceField source={source} reference={reference} label={label}>
                <TextField source="id_presentation" />
            </ReferenceField>
        );
    }

    const snapshot = record[snapshotSource];
    if (!snapshot) return null;

    return (
        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
            <DeletedSnapshotIndicator snapshot={snapshot} reference={reference} showLabel />
        </Box>
    );
};

export const DeletedSnapshotReferenceInput = ({ source, reference, snapshotSource, children, ...props }) => {
    const record = useRecordContext();
    const snapshot = record?.[snapshotSource];

    return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, width: '100%' }}>
            <ReferenceInput source={source} reference={reference} {...props} sx={{ flex: 1 }}>
                {children}
            </ReferenceInput>
            {snapshot && <DeletedSnapshotIndicator snapshot={snapshot} reference={reference} />}
        </Box>
    );
};
'''
