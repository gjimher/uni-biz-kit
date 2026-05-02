def generate() -> str:
    return """import React from 'react';
import {
  ResourceContextProvider,
  ListContextProvider,
  useList,
  useGetList,
} from 'react-admin';

export function CustomPage({ resource, children }) {
  const { data = [], total, isLoading } = useGetList(resource, {
    pagination: { page: 1, perPage: 25 },
    sort: { field: 'id', order: 'ASC' },
  });
  const listContext = useList({ data, total, isLoading });
  return (
    <ResourceContextProvider value={resource}>
      <ListContextProvider value={listContext}>
        {children}
      </ListContextProvider>
    </ResourceContextProvider>
  );
}
"""
