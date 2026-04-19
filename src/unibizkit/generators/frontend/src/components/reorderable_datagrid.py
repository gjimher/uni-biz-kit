def generate() -> str:
    return """import * as React from 'react';
import {
    Datagrid,
    DatagridBody,
    RecordContextProvider,
    useListContext,
    useUpdate,
    useNotify,
    useRefresh
} from 'react-admin';
import { TableRow, TableCell } from '@mui/material';
import { Reorder as DragHandleIcon } from '@mui/icons-material';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';

const DragHandle = ({ disabled }) => (
    <TableCell padding="none">
        <DragHandleIcon
            style={{
                cursor: disabled ? 'default' : 'grab',
                color: disabled ? '#eee' : '#999',
                marginLeft: '10px'
            }}
        />
    </TableCell>
);

const ReorderableDatagridRow = ({ record, id, index, isReorderable, children, ...rest }) => (
    <Draggable draggableId={String(id)} index={index} isDragDisabled={!isReorderable}>
        {(provided, snapshot) => (
            <TableRow
                ref={provided.innerRef}
                {...provided.draggableProps}
                {...(isReorderable ? provided.dragHandleProps : {})}
                style={{
                    ...provided.draggableProps.style,
                    backgroundColor: snapshot.isDragging ? '#eee' : 'white',
                    display: 'table-row',
                }}
                {...rest}
            >
                <DragHandle disabled={!isReorderable} />
                {React.Children.map(children, (field, i) => (
                    React.isValidElement(field) ? (
                        <RecordContextProvider value={record}>
                            <TableCell key={field.props.source || i}>
                                {field}
                            </TableCell>
                        </RecordContextProvider>
                    ) : null
                ))}
            </TableRow>
        )}
    </Draggable>
);

const ReorderableDatagridBody = ({ children, localData, isReorderable, ...rest }) => {
    const { isPending } = useListContext();
    if (isPending || !localData) return null;

    return (
        <Droppable droppableId="datagrid-body" isDropDisabled={!isReorderable}>
            {(provided) => (
                <tbody ref={provided.innerRef} {...provided.droppableProps} {...rest}>
                    {localData.map((record, index) => (
                        <ReorderableDatagridRow
                            key={record.id}
                            id={record.id}
                            index={index}
                            record={record}
                            isReorderable={isReorderable}
                        >
                            {children}
                        </ReorderableDatagridRow>
                    ))}
                    {provided.placeholder}
                </tbody>
            )}
        </Droppable>
    );
};

export const ReorderableDatagrid = ({ children, ...props }) => {
    const { data, resource, refetch, isPending, sort, setSort } = useListContext();
    const [localData, setLocalData] = React.useState(data);
    const [update] = useUpdate();
    const notify = useNotify();

    const isReorderable = sort && sort.field === 'part_of_order';

    // Force ASC order for part_of_order to keep UI consistent
    React.useEffect(() => {
        if (sort && sort.field === 'part_of_order' && sort.order === 'DESC') {
            setSort({ field: 'part_of_order', order: 'ASC' });
        }
    }, [sort, setSort]);

    React.useEffect(() => {
        if (data) {
            if (isReorderable) {
                // Force sort by part_of_order to ensure UI consistency
                // This protects against the list context returning unsorted data
                const sortedData = [...data].sort((a, b) => {
                    const orderA = (a.part_of_order !== undefined && a.part_of_order !== null) ? a.part_of_order : Number.MAX_SAFE_INTEGER;
                    const orderB = (b.part_of_order !== undefined && b.part_of_order !== null) ? b.part_of_order : Number.MAX_SAFE_INTEGER;
                    return orderA - orderB;
                });
                setLocalData(sortedData);
            } else {
                setLocalData(data);
            }
        }
    }, [data, isReorderable]);

    if (isPending || !localData) return null;

    const onDragEnd = async (result) => {
        if (!result.destination) return;
        if (result.destination.index === result.source.index) return;
        if (!isReorderable) return;

        const startIndex = result.source.index;
        const endIndex = result.destination.index;

        // 1. Calculate new order locally
        const reorderedData = Array.from(localData);
        const [removed] = reorderedData.splice(startIndex, 1);
        reorderedData.splice(endIndex, 0, removed);

        // 2. Map existing order values to the new positions
        const allOrders = localData
            .map((r, idx) => (r.part_of_order !== undefined && r.part_of_order !== null) ? r.part_of_order : idx)
            .sort((a, b) => a - b);

        const updates = [];
        const finalData = reorderedData.map((record, i) => {
            const targetOrder = allOrders[i];
            if (record.part_of_order !== targetOrder) {
                const updatedRecord = { ...record, part_of_order: targetOrder };
                updates.push(update(resource, {
                    id: record.id,
                    data: { part_of_order: targetOrder },
                    previousData: record
                }, { mutationMode: 'pessimistic' }));
                return updatedRecord;
            }
            return record;
        });

        // Update UI immediately
        setLocalData(finalData);

        try {
            if (updates.length > 0) {
                await Promise.all(updates);
                notify('Order updated', { type: 'info' });
            }
        } catch (error) {
            notify('Error updating order: ' + error.message, { type: 'warning' });
            setLocalData(data);
        }
    };


    return (
        <DragDropContext onDragEnd={onDragEnd}>
            <Datagrid {...props} body={<ReorderableDatagridBody localData={localData} isReorderable={isReorderable} />}>
                {children}
            </Datagrid>
        </DragDropContext>
    );
};
"""
