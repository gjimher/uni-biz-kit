import React from 'react';
import { Datagrid, TextField, NumberField } from 'react-admin';
import { Link } from 'react-router-dom';
import { CustomPage } from '../CustomPage';

export default function ExampleAdminPublic() {
  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <p><Link to="/">Home</Link></p>
      <h1>Products — public React-Admin components</h1>
      <p style={{ color: '#666' }}>
        Public page: accessible without login. Embeds a React-Admin{' '}
        <code>Datagrid</code> through the <code>CustomPage</code> wrapper,
        loading data via the <code>anon</code> Supabase role.
        See the <Link to="/priv/example-admin">authenticated version</Link> for comparison.
      </p>

      <CustomPage resource="product">
        <Datagrid bulkActionButtons={false}>
          <TextField source="name" label="Name" />
          <TextField source="sku" label="SKU" />
          <NumberField source="price" label="Price" />
        </Datagrid>
      </CustomPage>

      <p style={{ marginTop: 16 }}>
        <a href="#/admin/product">Manage in the Admin panel &rarr;</a>
      </p>
    </div>
  );
}
