import React from 'react';
import { Datagrid, TextField, NumberField } from 'react-admin';
import { Link } from 'react-router-dom';
import { CustomPage } from '../../CustomPage';

export default function ExampleAdmin() {
  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <p><Link to="/">Home</Link></p>
      <h1>Products - React-Admin components</h1>
      <p style={{ color: '#666' }}>
        JSX page with a custom layout that embeds a React-Admin <code>Datagrid</code>
        through the <code>CustomPage</code> wrapper.
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
