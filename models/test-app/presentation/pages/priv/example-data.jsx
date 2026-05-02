import React from 'react';
import { useGetList } from 'react-admin';
import { Link } from 'react-router-dom';

export default function ExampleData() {
  const { data: products, isPending, error } = useGetList('product', {
    pagination: { page: 1, perPage: 10 },
    sort: { field: 'name', order: 'ASC' },
  });

  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <p><Link to="/">Home</Link></p>
      <h1>Products - data with useGetList</h1>
      <p style={{ color: '#666' }}>
        Plain JSX page without React-Admin UI components.
        Data is loaded with the <code>useGetList</code> hook.
      </p>

      {isPending && <p>Loading...</p>}
      {error && <p style={{ color: 'red' }}>Error: {error.message}</p>}

      {products && (
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={th}>ID</th>
              <th style={th}>Name</th>
              <th style={th}>SKU</th>
              <th style={th}>Price</th>
            </tr>
          </thead>
          <tbody>
            {products.map(p => (
              <tr key={p.id}>
                <td style={td}>{p.id}</td>
                <td style={td}>{p.name}</td>
                <td style={td}>{p.sku}</td>
                <td style={td}>{p.price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p style={{ marginTop: 16 }}>
        <a href="#/admin/product">Manage in the Admin panel &rarr;</a>
      </p>
    </div>
  );
}

const th = { border: '1px solid #ddd', padding: '8px 12px', textAlign: 'left' };
const td = { border: '1px solid #ddd', padding: '8px 12px' };
