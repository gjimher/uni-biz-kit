def generate() -> str:
    return """import * as React from 'react';
import { useRecordContext } from 'react-admin';

export const Title = ({ name }) => {
    const record = useRecordContext();
    return (
        <span>
            {name} {record ? `${record.id_presentation}` : ''}
        </span>
    );
};
"""
