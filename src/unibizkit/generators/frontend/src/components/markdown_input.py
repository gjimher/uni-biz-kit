def generate() -> str:
    return """import React from 'react';
import MDEditor from '@uiw/react-md-editor';
import { useInput, useRecordContext, FieldTitle } from 'react-admin';
import { FormControl, FormHelperText, InputLabel } from '@mui/material';

// Form input for 'markdown' fields: toolbar + markdown source with live preview.
// The edit/live/preview buttons in the toolbar let the user switch between raw
// markdown and rendered (WYSIWYG-like) views.
const MarkdownInput = ({ source, label, validate, disabled, helperText, ...rest }) => {
  const { field, fieldState, isRequired } = useInput({ source, validate, ...rest });
  const error = fieldState.error?.message;

  return (
    <FormControl fullWidth margin="none" error={!!error} data-color-mode="light">
      <InputLabel shrink required={isRequired} sx={{ position: 'relative', transform: 'none', mb: 0.5 }}>
        {label ?? <FieldTitle source={source} />}
      </InputLabel>
      {disabled ? (
        <MDEditor.Markdown source={field.value || ''} />
      ) : (
        <MDEditor
          value={field.value || ''}
          onChange={(value) => field.onChange(value ?? '')}
          preview="live"
          height={300}
          textareaProps={{ onBlur: field.onBlur }}
        />
      )}
      {(error || helperText) && <FormHelperText>{error || helperText}</FormHelperText>}
    </FormControl>
  );
};

// Read-only rendering of a 'markdown' field for show views and list columns.
const MarkdownField = ({ source }) => {
  const record = useRecordContext();
  return (
    <div data-color-mode="light">
      <MDEditor.Markdown source={record?.[source] || ''} />
    </div>
  );
};

export { MarkdownInput, MarkdownField };
"""
