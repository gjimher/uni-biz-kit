def generate() -> str:
    return """import * as React from 'react';
import { Toolbar, SaveButton, DeleteButton, usePermissions } from 'react-admin';

export const CustomEditToolbar = ({ resource, workflowCanEdit = true, ...props }) => {
    const { permissions } = usePermissions();
    const roleCanEdit = permissions?.[resource]?.includes('write') || permissions?.['*']?.includes('write');
    const canEdit = roleCanEdit && workflowCanEdit;

    return (
        <Toolbar {...props}>
            <SaveButton disabled={!canEdit} />
            {roleCanEdit && <DeleteButton disabled={!workflowCanEdit} mutationMode="pessimistic" />}
        </Toolbar>
    );
};
"""
