import React, { useEffect, useState } from 'react';
import { supabaseClient } from '../../../supabaseClient';
import { money, formatDate } from '../../lib';
import { ACCENT, INK, MUTED, BORDER, BG_SOFT, FONT } from '../index.jsx';

// ---------------------------------------------------------------------------
// /priv/orders — the signed-in shopper's order history. RLS scopes the order
// table to the current customer, so a plain select returns only their orders.
// The order in state 'initial' is the live shopping cart and is not shown.
// ---------------------------------------------------------------------------

const STATE_COLORS = {
  checkout: '#f59e0b', confirmed: ACCENT, processing: '#0ea5e9',
  shipped: '#8b5cf6', delivered: '#10b981',
};

export default function MyOrders() {
  const [orders, setOrders] = useState(null); // null = loading

  useEffect(() => {
    supabaseClient.from('order')
      .select('id, id_presentation, order_date, state, payment_status, grand_total, '
        + 'order_item(id, product_name, quantity, unit_price, total_price)')
      .neq('state', 'initial')
      .order('id', { ascending: false })
      .then(({ data }) => setOrders(data ?? []));
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: BG_SOFT, fontFamily: FONT, color: INK }}>
      <div style={{ maxWidth: 860, margin: '0 auto', padding: '28px 20px 60px' }}>
        <a href="#/" style={{ textDecoration: 'none', color: MUTED, fontSize: 14, fontWeight: 600 }}>
          ← Back to shop
        </a>
        <h1 style={{ fontSize: 26, margin: '18px 0 22px' }}>My orders</h1>

        {orders === null && <p style={{ color: MUTED }}>Loading…</p>}
        {orders?.length === 0 && (
          <p style={{ color: MUTED }}>You have no orders yet. <a href="#/" style={{ color: ACCENT }}>Start shopping</a>.</p>
        )}

        {orders?.map((order) => (
          <div key={order.id} style={{
            background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 14,
            padding: '18px 20px', marginBottom: 16,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <div style={{ fontWeight: 700 }}>Order {order.id_presentation}</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Badge label={order.state} color={STATE_COLORS[order.state] ?? MUTED} />
                {order.payment_status && <Badge label={order.payment_status} color={order.payment_status === 'paid' ? '#10b981' : MUTED} />}
              </div>
            </div>
            {order.order_date && (
              <div style={{ color: MUTED, fontSize: 13, margin: '4px 0 12px' }}>
                {formatDate(order.order_date)}
              </div>
            )}
            {order.order_item.map((item) => (
              <div key={item.id} style={{
                display: 'flex', justifyContent: 'space-between', fontSize: 14,
                padding: '7px 0', borderTop: `1px solid ${BORDER}`,
              }}>
                <span>{item.product_name} × {item.quantity}</span>
                <span style={{ color: MUTED }}>{money(item.total_price)}</span>
              </div>
            ))}
            <div style={{
              display: 'flex', justifyContent: 'space-between', fontWeight: 700,
              paddingTop: 10, borderTop: `1px solid ${BORDER}`,
            }}>
              <span>Total</span>
              <span>{money(order.grand_total)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Badge({ label, color }) {
  return (
    <span style={{
      background: `${color}1a`, color, borderRadius: 999, padding: '3px 10px',
      fontSize: 12, fontWeight: 700, textTransform: 'capitalize',
    }}>{label}</span>
  );
}
