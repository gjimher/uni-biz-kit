def generate() -> str:
    return """import React from 'react';
import Tooltip from '@mui/material/Tooltip';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';

const FIELD_HELP_ICON = ({ label, help }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
    {label}
    <Tooltip title={help} placement="top">
      <HelpOutlineIcon sx={{ fontSize: 14, cursor: 'help' }} />
    </Tooltip>
  </span>
);

export { FIELD_HELP_ICON };
"""
