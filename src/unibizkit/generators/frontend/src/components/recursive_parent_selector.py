def generate() -> str:
    return """import * as React from 'react';
import {
    ReferenceField,
    TextField,
    ReferenceInput,
    AutocompleteInput,
    FormDataConsumer,
    useRecordContext
} from 'react-admin';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, Box, Typography } from '@mui/material';

export const RecursiveParentSelector = ({ source, reference, label, separator, displayField }) => {
    const [open, setOpen] = React.useState(false);
    const record = useRecordContext();

    // Filter out the current record to prevent self-referencing and cycles
    const filter = React.useMemo(() => {
        if (record && record.id) {
             // ra-data-postgrest expects 'field@op' syntax for custom operators
             const filters = { "id@neq": record.id };
             if (record[displayField]) {
                 filters["id_presentation@not.ilike"] = `%${separator}${record[displayField]}${separator}%`;
             }
             return filters;
        }
        return {};
    }, [record, separator, displayField]);

    return (
        <>
            <Box display="flex" alignItems="center" justifyContent="space-between" width="100%" sx={{ border: '1px solid #e0e0e0', borderRadius: 1, p: 1, minHeight: '56px', mb: 2 }}>
                <Box flexGrow={1}>
                    <Typography variant="caption" color="textSecondary" display="block">
                        {label}
                    </Typography>
                    <FormDataConsumer>
                        {({ formData }) => (
                             <ReferenceField source={source} reference={reference} record={formData} link={false}>
                                 <TextField source="id_presentation" />
                             </ReferenceField>
                        )}
                    </FormDataConsumer>
                </Box>
                <Button onClick={() => setOpen(true)} size="small" variant="outlined">Change</Button>
            </Box>
            <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
                <DialogTitle>Select {label}</DialogTitle>
                <DialogContent>
                    <Box pt={1}>
                        <ReferenceInput
                            source={source}
                            reference={reference}
                            sort={{ field: 'id_presentation', order: 'ASC' }}
                            filter={filter}
                        >
                            <AutocompleteInput
                                optionText="id_presentation"
                                filterToQuery={searchText => ({ "id_presentation@ilike": searchText })}
                                fullWidth
                                label={label}
                                onChange={() => setOpen(false)}
                            />
                        </ReferenceInput>
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>Close</Button>
                </DialogActions>
            </Dialog>
        </>
    );
};
"""
