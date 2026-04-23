def generate() -> str:
    return """import * as React from 'react';
import { useRecordContext } from 'react-admin';
import Tooltip from '@mui/material/Tooltip';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';

export const Title = ({ name, description }) => {
    const record = useRecordContext();
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {name} {record ? `${record.id_presentation}` : ''}
            {description && (
                <Tooltip title={description} placement="top">
                    <HelpOutlineIcon sx={{ fontSize: 16, cursor: 'help', color: 'inherit', opacity: 0.7 }} />
                </Tooltip>
            )}
        </span>
    );
};
"""
