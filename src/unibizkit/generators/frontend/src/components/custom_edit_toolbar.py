def generate() -> str:
    return """import * as React from 'react';
import { Toolbar, SaveButton, DeleteButton, usePermissions } from 'react-admin';

export const CustomEditToolbar = ({ resource, workflowCanEdit = true, workflowCanAssign = false, ...props }) => {
    const { permissions } = usePermissions();
    const roleCanEdit = permissions?.[resource]?.includes('write') || permissions?.['*']?.includes('write');
    // An assigner may save the task owner change even when the state makes the
    // record read-only for them (the DB trigger limits what they can touch).
    const canSave = roleCanEdit && (workflowCanEdit || workflowCanAssign);

    return (
        <Toolbar {...props}>
            <SaveButton disabled={!canSave} />
            {roleCanEdit && <DeleteButton disabled={!workflowCanEdit} mutationMode="pessimistic" />}
        </Toolbar>
    );
};
"""
