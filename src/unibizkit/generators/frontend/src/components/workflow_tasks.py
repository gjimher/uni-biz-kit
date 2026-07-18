def generate(customization: bool) -> str:
    """Admin task pages backed by the _workflow_tasks SQL view.

    Regular React-Admin lists (server-side filtering, sorting and pagination
    via PostgREST) over the UNION view of every workflow concept; the concept
    is one of the columns and each row links to the record's edit form. The
    toolbar matches the generated resource lists (add filter, configurable
    columns, reset, export).
    """
    template = """import * as React from 'react';
import {
    DatagridConfigurable,
    DateField,
    ExportButton,
    FilterButton,
    List,
    SelectColumnsButton,
    SelectInput,
    TextField,
    TextInput,
    TopToolbar,
    useDataProvider,
    useGetIdentity,
    useListContext,
    useNotify,
    useRecordContext,
} from 'react-admin';
import { Button, Typography } from '@mui/material';
import { RESET_COLUMNS_BUTTON } from './quick_edit';
__CUSTOM_IMPORT__import { CONCEPT_WORKFLOWS } from '../workflowConfig';

const conceptChoices = Object.keys(CONCEPT_WORKFLOWS).map(concept => ({
    id: concept,
    name: concept.replaceAll('_', ' '),
}));
__FILTERS_BLOCK__

const TaskListActions = ({ preferenceKey }) => (
    <TopToolbar>
        <FilterButton />
        <SelectColumnsButton preferenceKey={preferenceKey} />
        <RESET_COLUMNS_BUTTON preferenceKey={preferenceKey} />
        <ExportButton />
    </TopToolbar>
);

// Rows link to the underlying record's edit form; the custom admin router
// prefixes /admin for resource paths.
const rowClickToRecord = (id, resource, record) => `/${record.concept}/${record.record_id}`;

const TakeButton = () => {
    const record = useRecordContext();
    const dataProvider = useDataProvider();
    const notify = useNotify();
    const { refetch } = useListContext();
    const { data: identity } = useGetIdentity();
    if (!record) return null;
    return (
        <Button
            size="small"
            variant="outlined"
            onClick={async (event) => {
                event.stopPropagation();
                try {
                    await dataProvider.update(record.concept, {
                        id: record.record_id,
                        data: { state_task_owner: (identity?.email || '').toLowerCase() },
                        previousData: { ...record, id: record.record_id },
                    });
                    notify('Task assigned to you', { type: 'info' });
                    refetch();
                } catch (error) {
                    notify(error?.message || 'Could not assign task', { type: 'warning' });
                }
            }}
        >
            Assign to me
        </Button>
    );
};

export const WORKFLOW_ASSIGNABLE_TASKS = () => {
    const { data: identity, isLoading } = useGetIdentity();
__TASK_FILTERS_HOOK__    if (isLoading) return null;
    const roles = identity?.roles || [];
    if (roles.length === 0) {
        return (
            <Typography variant="body2" sx={{ p: 2 }}>
                You cannot assign tasks in any workflow state.
            </Typography>
        );
    }
    const preferenceKey = 'workflow_tasks_assignable.datagrid';
    return (
        <List
            resource="_workflow_tasks"
            storeKey="workflow_tasks_assignable"
            title="Assignable workflow tasks"
            filter={{ 'state_task_owner@is': null, 'assigners@ov': `{${roles.join(',')}}` }}
            filters={taskFilters}
            sort={{ field: '_updated_at', order: 'DESC' }}
            actions={<TaskListActions preferenceKey={preferenceKey} />}
            empty={false}
        >
            <DatagridConfigurable preferenceKey={preferenceKey} rowClick={rowClickToRecord} bulkActionButtons={false}>
                <TextField source="concept" />
                <TextField source="id_presentation" label="Id" />
                <TextField source="state" />
                <DateField source="_updated_at" label="Updated" showTime />
                <TakeButton label="Assign" />
            </DatagridConfigurable>
        </List>
    );
};

export const WORKFLOW_MY_TASKS = () => {
    const { data: identity, isLoading } = useGetIdentity();
__TASK_FILTERS_HOOK__    if (isLoading || !identity?.email) return null;
    const preferenceKey = 'workflow_tasks_mine.datagrid';
    return (
        <List
            resource="_workflow_tasks"
            storeKey="workflow_tasks_mine"
            title="My workflow tasks"
            filter={{ state_task_owner: identity.email.toLowerCase() }}
            filters={taskFilters}
            sort={{ field: '_updated_at', order: 'DESC' }}
            actions={<TaskListActions preferenceKey={preferenceKey} />}
            empty={false}
        >
            <DatagridConfigurable preferenceKey={preferenceKey} rowClick={rowClickToRecord} bulkActionButtons={false}>
                <TextField source="concept" />
                <TextField source="id_presentation" label="Id" />
                <TextField source="state" />
                <DateField source="_updated_at" label="Updated" showTime />
            </DatagridConfigurable>
        </List>
    );
};
"""

    _runtime_filters = (
        "// The state filter choices honor the per-role hidden workflow states from the\n"
        "// presentation customization overlays, so they must be computed at runtime.\n"
        "const useTaskFilters = () => {\n"
        "    const custom = useCustomization();\n"
        "    return React.useMemo(() => {\n"
        "        const stateChoices = [...new Set(\n"
        "            Object.entries(CONCEPT_WORKFLOWS).flatMap(([concept, workflow]) => {\n"
        "                const hidden = custom && custom.hiddenStates[concept];\n"
        "                return workflow.states\n"
        "                    .map(state => state.name)\n"
        "                    .filter(name => !(hidden && hidden.has(name)));\n"
        "            })\n"
        "        )].map(state => ({ id: state, name: state }));\n"
        "        return [\n"
        "            <SelectInput key=\"concept\" source=\"concept\" choices={conceptChoices} />,\n"
        "            <SelectInput key=\"state\" source=\"state\" choices={stateChoices} />,\n"
        "            <TextInput\n"
        "                key=\"search\"\n"
        "                label=\"Search\"\n"
        "                source=\"id_presentation@ilike\"\n"
        "                parse={(value) => (value ? `%${value}%` : value)}\n"
        "                format={(value) => (value ? value.replaceAll('%', '') : value)}\n"
        "            />,\n"
        "        ];\n"
        "    }, [custom]);\n"
        "};"
    )
    _static_filters = (
        "const stateChoices = [...new Set(\n"
        "    Object.values(CONCEPT_WORKFLOWS).flatMap(workflow => workflow.states.map(state => state.name))\n"
        ")].map(state => ({ id: state, name: state }));\n"
        "\n"
        "const taskFilters = [\n"
        "    <SelectInput key=\"concept\" source=\"concept\" choices={conceptChoices} />,\n"
        "    <SelectInput key=\"state\" source=\"state\" choices={stateChoices} />,\n"
        "    <TextInput\n"
        "        key=\"search\"\n"
        "        label=\"Search\"\n"
        "        source=\"id_presentation@ilike\"\n"
        "        parse={(value) => (value ? `%${value}%` : value)}\n"
        "        format={(value) => (value ? value.replaceAll('%', '') : value)}\n"
        "    />,\n"
        "];"
    )
    if customization:
        custom_import = "import { useCustomization } from './customization';\n"
        filters_block = "\n" + _runtime_filters
        task_filters_hook = "    const taskFilters = useTaskFilters();\n"
    else:
        custom_import = ""
        filters_block = _static_filters
        task_filters_hook = ""
    return (
        template
        .replace("__CUSTOM_IMPORT__", custom_import)
        .replace("__FILTERS_BLOCK__", filters_block)
        .replace("__TASK_FILTERS_HOOK__", task_filters_hook)
    )
