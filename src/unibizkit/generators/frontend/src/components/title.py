_TEMPLATE = """import * as React from 'react';
import { useRecordContext } from 'react-admin';
import Tooltip from '@mui/material/Tooltip';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
__CUSTOM_IMPORT__
export const Title = ({ name, description }) => {
    const record = useRecordContext();
__CUSTOM_LABEL__    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {__LABEL__} {record ? `${record.id_presentation}` : ''}
            {description && (
                <Tooltip title={description} placement="top">
                    <HelpOutlineIcon sx={{ fontSize: 16, cursor: 'help', color: 'inherit', opacity: 0.7 }} />
                </Tooltip>
            )}
        </span>
    );
};
"""

_CUSTOM_LABEL = """    const custom = useCustomization();
    // Presentation customization overlays can rename the page title per role.
    const label = (custom && custom.labels.titles[name]) || name;
"""


def generate(customization: bool) -> str:
    if customization:
        custom_import = "import { useCustomization } from './customization';\n"
        custom_label = _CUSTOM_LABEL
        label = "label"
    else:
        custom_import = ""
        custom_label = ""
        label = "name"
    return (
        _TEMPLATE
        .replace("__CUSTOM_IMPORT__", custom_import)
        .replace("__CUSTOM_LABEL__", custom_label)
        .replace("__LABEL__", label)
    )
