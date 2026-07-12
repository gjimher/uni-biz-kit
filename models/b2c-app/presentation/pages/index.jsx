import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { supabaseClient } from '../../supabaseClient';
import {
  useSession, money, publicUrl, transition, getProfile,
  createPaymentIntent, confirmPayment, paymentsDevMode,
  validateRecord, optionsFor, firstValidationForSource, FREE_ENTRY_OPTION,
} from '../lib';

// ---------------------------------------------------------------------------
// B2C storefront — catalog, cart and a complete checkout (place order) flow.
// Product cover images are served from the public `product-documents` bucket.
// Cross-cutting concerns (session, money formatting, storage URLs, workflow
// transitions and address validation) come from the generated `../lib` helpers.
// ---------------------------------------------------------------------------

export const ACCENT = '#6366f1';
export const ACCENT_DARK = '#4f46e5';
export const INK = '#1e293b';
export const MUTED = '#64748b';
export const BORDER = '#e2e8f0';
export const BG_SOFT = '#f8fafc';
export const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export default function StorefrontHome() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const session = useSession(); // undefined = loading, null = signed out
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [products, setProducts] = useState([]);
  const [loadingProducts, setLoadingProducts] = useState(true);

  const [cart, setCart] = useState(null);       // { id, items: [...] }
  const [cartOpen, setCartOpen] = useState(false);
  const [checkout, setCheckout] = useState(false);
  const [placedOrder, setPlacedOrder] = useState(null);

  // -- categories -----------------------------------------------------------
  useEffect(() => {
    supabaseClient
      .from('category')
      .select('id, name, parent, is_active')
      .eq('is_active', true)
      .order('name')
      .then(({ data }) => setCategories(data ?? []));
  }, []);

  const rootCategories = useMemo(() => categories.filter((c) => c.parent == null), [categories]);

  // ids of the selected category + all of its descendants
  const categoryFilterIds = useMemo(() => {
    if (selectedCategory == null) return null;
    const childrenOf = {};
    categories.forEach((c) => {
      if (c.parent != null) (childrenOf[c.parent] ??= []).push(c.id);
    });
    const ids = [];
    const stack = [selectedCategory];
    while (stack.length) {
      const id = stack.pop();
      ids.push(id);
      (childrenOf[id] ?? []).forEach((c) => stack.push(c));
    }
    return ids;
  }, [selectedCategory, categories]);

  // -- products -------------------------------------------------------------
  const fetchProducts = useCallback(async () => {
    setLoadingProducts(true);
    let query = supabaseClient
      .from('product')
      .select(
        'id, name, description, category, ' +
        'product_variant(id, name, price, stock_quantity, size, color, is_available), ' +
        'product_document(tag, storage_path, is_current)'
      )
      .eq('status', 'published')
      .order('is_featured', { ascending: false })
      .order('name');
    if (categoryFilterIds) query = query.in('category', categoryFilterIds);
    const { data } = await query;
    setProducts(data ?? []);
    setLoadingProducts(false);
  }, [categoryFilterIds]);

  useEffect(() => { fetchProducts(); }, [fetchProducts]);

  // -- cart -----------------------------------------------------------------
  const fetchCart = useCallback(async () => {
    if (!session) { setCart(null); return; }
    const { data: order } = await supabaseClient
      .from('order')
      .select('id, state, order_item(id, part_of_order, quantity, unit_price, total_price, product_name, variant)')
      .eq('state', 'initial')
      .order('id', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (!order) { setCart({ id: null, items: [] }); return; }
    // Sort by part_of_order (a SERIAL column) for a stable insertion order that
    // does not change when an item's quantity is updated.
    const items = (order.order_item ?? []).slice().sort((a, b) => a.part_of_order - b.part_of_order);
    setCart({ id: order.id, items });
  }, [session]);

  useEffect(() => { fetchCart(); }, [fetchCart]);

  // After returning from login (?add=<variantId>), add the remembered variant,
  // open the cart and drop the query param so a refresh does not re-add it.
  const pendingAddRef = useRef(false);
  useEffect(() => {
    if (!session || cart === null || pendingAddRef.current) return;
    const add = searchParams.get('add');
    if (!add) return;
    pendingAddRef.current = true;
    addToCart(Number(add)).finally(() => setSearchParams({}, { replace: true }));
  }, [session, cart, searchParams]); // eslint-disable-line

  const cartCount = (cart?.items ?? []).reduce((s, i) => s + (i.quantity ?? 0), 0);
  const cartSubtotal = (cart?.items ?? []).reduce((s, i) => s + Number(i.total_price ?? 0), 0);

  // -- cart mutations -------------------------------------------------------
  async function ensureCart() {
    if (cart?.id) return cart.id;
    const { data, error } = await supabaseClient
      .from('order')
      .insert({ state: 'initial' })   // customer is auto-filled by a DB trigger
      .select('id')
      .single();
    if (error) throw error;
    setCart({ id: data.id, items: [] });
    return data.id;
  }

  async function addToCart(variantId) {
    if (!session) {
      // Bounce to the storefront sign-in, remembering the variant so it is added on return.
      navigate('/signin?redirectTo=' + encodeURIComponent('#/?add=' + variantId));
      return;
    }
    const orderId = await ensureCart();
    const existing = (cart?.items ?? []).find((i) => i.variant === variantId);
    if (existing) {
      await supabaseClient.from('order_item')
        .update({ quantity: existing.quantity + 1 }).eq('id', existing.id);
    } else {
      const { error } = await supabaseClient.from('order_item')
        .insert({ order: orderId, variant: variantId, quantity: 1 });
      if (error) { alert('Could not add item: ' + error.message); return; }
    }
    await fetchCart();
    setCartOpen(true);
  }

  async function setItemQuantity(item, quantity) {
    if (quantity <= 0) {
      await supabaseClient.from('order_item').delete().eq('id', item.id);
    } else {
      await supabaseClient.from('order_item').update({ quantity }).eq('id', item.id);
    }
    await fetchCart();
  }

  function onOrderPlaced(order) {
    setCheckout(false);
    setCartOpen(false);
    setPlacedOrder(order);
    setCart({ id: null, items: [] });
    fetchCart();
  }

  // -- render ---------------------------------------------------------------
  return (
    <div style={{ fontFamily: FONT, color: INK, minHeight: '100vh', background: '#fff' }}>
      <Header
        session={session}
        cartCount={cartCount}
        onCartClick={() => setCartOpen(true)}
        navigate={navigate}
      />

      <main style={{ maxWidth: 1180, margin: '0 auto', padding: '0 20px 80px' }}>
        <Hero />

        <CategoryBar
          roots={rootCategories}
          selected={selectedCategory}
          onSelect={setSelectedCategory}
        />

        {loadingProducts ? (
          <Centered>Loading products…</Centered>
        ) : products.length === 0 ? (
          <Centered>No products found in this category.</Centered>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
            gap: 24, marginTop: 28,
          }}>
            {products.map((p) => (
              <ProductCard key={p.id} product={p} onAdd={addToCart} />
            ))}
          </div>
        )}
      </main>

      {cartOpen && (
        <CartDrawer
          cart={cart}
          subtotal={cartSubtotal}
          onClose={() => setCartOpen(false)}
          onQty={setItemQuantity}
          onCheckout={() => { setCartOpen(false); setCheckout(true); }}
        />
      )}

      {checkout && (
        <CheckoutOverlay
          cart={cart}
          subtotal={cartSubtotal}
          onClose={() => setCheckout(false)}
          onPlaced={onOrderPlaced}
        />
      )}

      {placedOrder && (
        <ConfirmationOverlay order={placedOrder} onClose={() => setPlacedOrder(null)} />
      )}
    </div>
  );
}

// ===========================================================================
// Header & Hero
// ===========================================================================

function Header({ session, cartCount, onCartClick, navigate }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20, background: 'rgba(255,255,255,0.9)',
      backdropFilter: 'blur(8px)', borderBottom: `1px solid ${BORDER}`,
    }}>
      <div style={{
        maxWidth: 1180, margin: '0 auto', padding: '14px 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 800, fontSize: 20 }}>
          <span style={{
            display: 'inline-flex', width: 32, height: 32, borderRadius: 9,
            background: `linear-gradient(135deg, ${ACCENT}, #0ea5e9)`, color: '#fff',
            alignItems: 'center', justifyContent: 'center', fontSize: 18,
          }}>🛍️</span>
          Nova Shop
        </div>
        <div style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
          {session === undefined ? null : session ? (
            <>
              {(session.user?.app_metadata?.roles ?? []).includes('admin') ? (
                <a href="#/admin" style={linkStyle}>Admin</a>
              ) : (
                <AccountMenu />
              )}
              <span onClick={() => supabaseClient.auth.signOut()}
                style={{ cursor: 'pointer', color: MUTED, fontSize: 14 }}>Sign out</span>
            </>
          ) : (
            <>
              <a href="#/signin" style={linkStyle}>Log in</a>
              <a href="#/register" style={{ ...linkStyle, ...primaryLink }}>Register</a>
            </>
          )}
          <button onClick={onCartClick} style={cartButtonStyle} aria-label="Open cart">
            🛒
            {cartCount > 0 && (
              <span style={cartBadgeStyle}>{cartCount}</span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}

// Account dropdown for regular (non-admin) shoppers: their orders and profile.
function AccountMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <span onClick={() => setOpen((o) => !o)} style={{ ...linkStyle, cursor: 'pointer' }}>
        My account ▾
      </span>
      {open && (
        <div style={{
          position: 'absolute', right: 0, top: 'calc(100% + 10px)', zIndex: 40,
          background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 10,
          boxShadow: '0 12px 30px rgba(15,23,42,0.18)', padding: 6,
          minWidth: 170, display: 'flex', flexDirection: 'column',
        }}>
          <a href="#/priv/orders" style={menuItemStyle} onClick={() => setOpen(false)}>My orders</a>
          <a href="#/priv/account" style={menuItemStyle} onClick={() => setOpen(false)}>My profile</a>
        </div>
      )}
    </div>
  );
}

function Hero() {
  return (
    <section style={{
      margin: '28px 0 8px', padding: '44px 40px', borderRadius: 20,
      background: `linear-gradient(135deg, ${ACCENT} 0%, #0ea5e9 100%)`,
      color: '#fff', position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'relative', zIndex: 1, maxWidth: 560 }}>
        <div style={{ fontSize: 13, letterSpacing: 1.5, textTransform: 'uppercase', opacity: 0.85 }}>
          New season · Free returns
        </div>
        <h1 style={{ margin: '10px 0 12px', fontSize: 38, lineHeight: 1.1, fontWeight: 800 }}>
          Everything you love, delivered fast.
        </h1>
        <p style={{ margin: 0, fontSize: 16, opacity: 0.92 }}>
          Tech, apparel and home essentials — handpicked and ready to ship.
          Use code <strong>WELCOME10</strong> for 10% off your first order.
        </p>
      </div>
      <div style={{
        position: 'absolute', right: -40, top: -40, width: 280, height: 280,
        borderRadius: '50%', background: 'rgba(255,255,255,0.12)',
      }} />
      <div style={{
        position: 'absolute', right: 90, bottom: -70, width: 200, height: 200,
        borderRadius: '50%', background: 'rgba(255,255,255,0.10)',
      }} />
    </section>
  );
}

function CategoryBar({ roots, selected, onSelect }) {
  return (
    <div style={{ display: 'flex', gap: 10, marginTop: 26, flexWrap: 'wrap' }}>
      <Chip label="All" active={selected == null} onClick={() => onSelect(null)} />
      {roots.map((c) => (
        <Chip key={c.id} label={c.name} active={selected === c.id} onClick={() => onSelect(c.id)} />
      ))}
    </div>
  );
}

function Chip({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: '8px 16px', borderRadius: 999, cursor: 'pointer', fontSize: 14, fontWeight: 600,
      border: `1px solid ${active ? ACCENT : BORDER}`,
      background: active ? ACCENT : '#fff', color: active ? '#fff' : INK,
      transition: 'all .15s',
    }}>{label}</button>
  );
}

// ===========================================================================
// Product card
// ===========================================================================

function ProductCard({ product, onAdd }) {
  const variants = (product.product_variant ?? []).filter((v) => v.is_available);
  const inStock = variants.filter((v) => v.stock_quantity > 0);
  const [variantId, setVariantId] = useState(() => inStock[0]?.id ?? variants[0]?.id ?? null);
  const [adding, setAdding] = useState(false);

  const prices = variants.map((v) => Number(v.price)).filter((p) => !isNaN(p));
  const minPrice = prices.length ? Math.min(...prices) : null;
  const multiPrice = prices.length > 1 && Math.min(...prices) !== Math.max(...prices);

  const cover = (product.product_document ?? []).find((d) => d.tag === 'img_m' && d.is_current)
    ?? (product.product_document ?? []).find((d) => d.tag === 'img_m');
  const imgUrl = publicUrl('product-documents', cover?.storage_path);

  function variantLabel(v) {
    return [v.name, v.size?.toUpperCase(), v.color].filter(Boolean).join(' · ');
  }

  async function handleAdd() {
    if (!variantId) return;
    setAdding(true);
    try { await onAdd(variantId); } finally { setAdding(false); }
  }

  return (
    <div style={{
      border: `1px solid ${BORDER}`, borderRadius: 16, overflow: 'hidden',
      display: 'flex', flexDirection: 'column', background: '#fff',
      boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
    }}>
      <div style={{ aspectRatio: '1 / 1', background: BG_SOFT }}>
        {imgUrl ? (
          <img src={imgUrl} alt={product.name}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        ) : (
          <div style={{
            width: '100%', height: '100%', display: 'flex',
            alignItems: 'center', justifyContent: 'center', color: '#cbd5e1', fontSize: 13,
          }}>No image</div>
        )}
      </div>
      <div style={{ padding: 16, flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>{product.name}</div>
        {product.description && (
          <div style={{ fontSize: 13, color: MUTED, flex: 1, lineHeight: 1.4 }}>
            {product.description.length > 84 ? product.description.slice(0, 84) + '…' : product.description}
          </div>
        )}
        <div style={{ fontSize: 18, fontWeight: 800, color: INK }}>
          {minPrice != null ? `${multiPrice ? 'From ' : ''}${money(minPrice)}` : '—'}
        </div>
        {inStock.length > 1 && (
          <select value={variantId ?? ''} onChange={(e) => setVariantId(Number(e.target.value))}
            style={{
              padding: '8px 10px', borderRadius: 9, border: `1px solid ${BORDER}`,
              fontSize: 13, color: INK, background: '#fff',
            }}>
            {inStock.map((v) => (
              <option key={v.id} value={v.id}>{variantLabel(v)} — {money(v.price)}</option>
            ))}
          </select>
        )}
        <button disabled={!inStock.length || adding} onClick={handleAdd}
          style={{
            marginTop: 4, padding: '11px 0', border: 'none', borderRadius: 10,
            fontWeight: 700, fontSize: 14, color: '#fff',
            cursor: inStock.length ? 'pointer' : 'default',
            background: inStock.length ? ACCENT : '#cbd5e1',
          }}>
          {!inStock.length ? 'Out of stock' : adding ? 'Adding…' : 'Add to cart'}
        </button>
      </div>
    </div>
  );
}

// ===========================================================================
// Cart drawer
// ===========================================================================

function CartDrawer({ cart, subtotal, onClose, onQty, onCheckout }) {
  const items = cart?.items ?? [];
  return (
    <Overlay onClose={onClose} align="flex-end">
      <aside onClick={(e) => e.stopPropagation()} style={{
        width: 'min(420px, 100%)', height: '100%', background: '#fff',
        display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 30px rgba(15,23,42,0.15)',
      }}>
        <DrawerHeader title={`Your cart (${items.reduce((s, i) => s + i.quantity, 0)})`} onClose={onClose} />
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 20px' }}>
          {items.length === 0 ? (
            <div style={{ color: MUTED, textAlign: 'center', padding: '60px 0' }}>
              Your cart is empty.
            </div>
          ) : items.map((item) => (
            <div key={item.id} style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '14px 0',
              borderBottom: `1px solid ${BORDER}`,
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{item.product_name ?? 'Item'}</div>
                <div style={{ color: MUTED, fontSize: 13 }}>{money(item.unit_price)} each</div>
              </div>
              <QtyStepper value={item.quantity} onChange={(q) => onQty(item, q)} />
              <div style={{ width: 70, textAlign: 'right', fontWeight: 700, fontSize: 14 }}>
                {money(item.total_price)}
              </div>
            </div>
          ))}
        </div>
        <div style={{ borderTop: `1px solid ${BORDER}`, padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14, fontSize: 15 }}>
            <span style={{ color: MUTED }}>Subtotal</span>
            <strong>{money(subtotal)}</strong>
          </div>
          <button disabled={!items.length} onClick={onCheckout} style={{
            width: '100%', padding: '13px 0', border: 'none', borderRadius: 11,
            background: items.length ? ACCENT : '#cbd5e1', color: '#fff',
            fontWeight: 700, fontSize: 15, cursor: items.length ? 'pointer' : 'default',
          }}>Checkout</button>
        </div>
      </aside>
    </Overlay>
  );
}

function QtyStepper({ value, onChange }) {
  const btn = {
    width: 28, height: 28, borderRadius: 8, border: `1px solid ${BORDER}`,
    background: '#fff', cursor: 'pointer', fontSize: 16, lineHeight: 1, color: INK,
  };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <button style={btn} onClick={() => onChange(value - 1)}>−</button>
      <span style={{ minWidth: 18, textAlign: 'center', fontSize: 14 }}>{value}</span>
      <button style={btn} onClick={() => onChange(value + 1)}>+</button>
    </div>
  );
}

// ===========================================================================
// Checkout
// ===========================================================================

const SHIPPING_FALLBACK = []; // loaded from DB

// --- Shared address-form helpers (checkout overlay and /priv/account page) ---
// Options for a ComboField column: only the combinations still compatible with
// the other filled-in fields, mirroring the admin's autocomplete.
export function addressComboProps(col, form) {
  const validation = firstValidationForSource('address', col);
  if (!validation) return { options: [], allowFree: true };
  const { options } = optionsFor(validation, col, form);
  return {
    options: options.filter((o) => o !== FREE_ENTRY_OPTION),
    allowFree: options.includes(FREE_ENTRY_OPTION),
  };
}

// Sets a column and auto-fills the other validation columns that collapse to a
// single concrete option (e.g. picking a city fills state/province and country).
export function setAddressField(form, col, value) {
  const next = { ...form, [col]: value };
  const validation = firstValidationForSource('address', col);
  if (!validation || !value) return next;
  for (const column of validation.columns) {
    if (next[column]) continue;
    const { options } = optionsFor(validation, column, next);
    const concrete = options.filter((o) => o !== FREE_ENTRY_OPTION);
    if (options.length === 1 && concrete.length === 1) next[column] = concrete[0];
  }
  return next;
}

// Clearing a field also clears the more specific fields below it, so the
// cascade never keeps an incompatible value (country → state → city).
export function clearAddressField(form, col) {
  const next = { ...form, [col]: '' };
  const order = ['country', 'state_province', 'city'];
  for (const dep of order.slice(order.indexOf(col) + 1)) next[dep] = '';
  return next;
}

function CheckoutOverlay({ cart, subtotal, onClose, onPlaced }) {
  const [form, setForm] = useState({
    first_name: '', last_name: '', street_line_1: '', street_line_2: '',
    city: '', state_province: '', postal_code: '', country: '',
  });
  const [shippingMethods, setShippingMethods] = useState(SHIPPING_FALLBACK);
  const [shippingId, setShippingId] = useState(null);
  const [couponCode, setCouponCode] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Two-step checkout: shipping details first, then payment (dev simulator or Stripe).
  const [step, setStep] = useState('details'); // 'details' | 'payment'
  const [intent, setIntent] = useState(null);  // { reference, amount, currency, status }

  // Prefill the shipping name from the customer profile (saved at registration).
  // The names may still be empty when the profile was auto-created without metadata.
  useEffect(() => {
    getProfile().then((profile) => {
      if (!profile) return;
      const { first_name: firstName, last_name: lastName } = profile.record;
      setForm((f) => ({
        ...f,
        first_name: f.first_name || firstName || '',
        last_name: f.last_name || lastName || '',
      }));
    });
  }, []);

  // Saved addresses (prefill). RLS scopes the address table to the current
  // customer, so a plain select returns only the shopper's own addresses.
  const [savedAddresses, setSavedAddresses] = useState([]);
  const [customerId, setCustomerId] = useState(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    supabaseClient.from('shipping_method')
      .select('id, name, carrier, base_cost, estimated_days_min, estimated_days_max')
      .eq('is_active', true).order('base_cost')
      .then(({ data }) => {
        setShippingMethods(data ?? []);
        if (data?.length) setShippingId(data[0].id);
      });
  }, []);

  const reloadAddresses = useCallback(() => {
    supabaseClient.from('address')
      .select('id, label, first_name, last_name, street_line_1, street_line_2, city, state_province, postal_code, country')
      .order('label')
      .then(({ data }) => setSavedAddresses(data ?? []));
  }, []);
  useEffect(() => { reloadAddresses(); }, [reloadAddresses]);

  // The cart order has its customer auto-filled by a DB trigger; read it so a
  // newly saved address can be linked to the right customer.
  useEffect(() => {
    if (!cart?.id) return;
    supabaseClient.from('order').select('customer').eq('id', cart.id).maybeSingle()
      .then(({ data }) => setCustomerId(data?.customer ?? null));
  }, [cart?.id]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const chosenShipping = shippingMethods.find((m) => m.id === shippingId);
  const shippingCost = chosenShipping ? Number(chosenShipping.base_cost) : 0;

  // Cascading country/state/city selector, driven by validations/address.csv
  // (shared helpers below, also used by the account page).
  const addrOptions = (col) => addressComboProps(col, form);
  const setAddr = (col) => (value) => setForm((f) => setAddressField(f, col, value));
  const clearAddr = (col) => () => setForm((f) => clearAddressField(f, col));

  const loadAddress = (e) => {
    const rec = savedAddresses.find((r) => r.id === Number(e.target.value));
    if (!rec) return;
    setForm({
      first_name: rec.first_name ?? '', last_name: rec.last_name ?? '',
      street_line_1: rec.street_line_1 ?? '', street_line_2: rec.street_line_2 ?? '',
      city: rec.city ?? '', state_province: rec.state_province ?? '',
      postal_code: rec.postal_code ?? '', country: rec.country ?? '',
    });
  };

  // The form keys (country/state_province/city) match the address validation
  // columns, so the shared validator can check the combination directly.
  const addrValid = Object.keys(validateRecord('address', form)).length === 0;

  const required = ['first_name', 'last_name', 'street_line_1', 'city', 'state_province', 'postal_code', 'country'];
  const valid = required.every((k) => form[k].trim()) && shippingId != null && addrValid;
  const canSave = required.every((k) => form[k].trim()) && addrValid && customerId != null;

  async function saveAddress() {
    if (!canSave || !saveName.trim()) return;
    setSaving(true);
    setError(null);
    const { error: insErr } = await supabaseClient.from('address').insert({
      customer: customerId,
      label: saveName.trim(),
      first_name: form.first_name,
      last_name: form.last_name,
      street_line_1: form.street_line_1,
      street_line_2: form.street_line_2 || null,
      city: form.city,
      state_province: form.state_province,
      postal_code: form.postal_code,
      country: form.country,
    });
    setSaving(false);
    if (insErr) { setError(insErr.message); return; }
    setSaveOpen(false);
    setSaveName('');
    reloadAddresses();
  }

  // Wait until the async order-compute-totals rule has caught up with the cart:
  // grand_total must match the total recomputed from its synchronous inputs
  // (subtotal rollup, shipping_costs copy, coupon snapshots).
  async function waitForGrandTotal() {
    for (let i = 0; i < 10; i++) {
      const { data } = await supabaseClient.from('order')
        .select('grand_total, subtotal, shipping_costs, coupon_snapshot_type, coupon_snapshot_value')
        .eq('id', cart.id).maybeSingle();
      if (data) {
        const sub = Number(data.subtotal ?? 0);
        const ship = Number(data.shipping_costs ?? 0);
        const discount = data.coupon_snapshot_type === 'percentage'
          ? sub * Number(data.coupon_snapshot_value ?? 0) / 100
          : data.coupon_snapshot_type === 'fixed' ? Number(data.coupon_snapshot_value ?? 0) : 0;
        if (data.grand_total != null && Math.abs(Number(data.grand_total) - (sub + ship - discount)) < 0.005) {
          return;
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    throw new Error('The order total is still being computed. Please try again.');
  }

  // Step 1 submit: write the details onto the cart order, then create the
  // payment intent for the resulting grand_total and switch to the payment step.
  async function continueToPayment() {
    setError(null);
    if (!valid) {
      setError(addrValid
        ? 'Please fill in all required fields.'
        : 'This country / state / city combination is not recognized.');
      return;
    }
    setSubmitting(true);
    try {
      // 1. Resolve an optional coupon code → id (snapshots are copied by DB triggers).
      let couponId = null;
      if (couponCode.trim()) {
        const { data: c } = await supabaseClient.from('coupon')
          .select('id').eq('code', couponCode.trim().toUpperCase()).eq('is_active', true).maybeSingle();
        if (!c) { setError(`Coupon "${couponCode}" is not valid.`); setSubmitting(false); return; }
        couponId = c.id;
      }

      // 2. Write address, shipping method and coupon onto the cart order (state 'initial').
      const { error: upErr } = await supabaseClient.from('order').update({
        shipping_address_first_name: form.first_name,
        shipping_address_last_name: form.last_name,
        shipping_address_street_line_1: form.street_line_1,
        shipping_address_street_line_2: form.street_line_2 || null,
        shipping_address_city: form.city,
        shipping_address_state_province: form.state_province,
        shipping_address_postal_code: form.postal_code,
        shipping_address_country: form.country,
        billing_address_first_name: form.first_name,
        billing_address_last_name: form.last_name,
        billing_address_street_line_1: form.street_line_1,
        billing_address_city: form.city,
        billing_address_postal_code: form.postal_code,
        billing_address_country: form.country,
        shipping_method: shippingId,
        coupon: couponId,
        notes: notes || null,
      }).eq('id', cart.id);
      if (upErr) throw upErr;

      // 3. Charge grand_total: wait for the async recompute, then open an intent.
      await waitForGrandTotal();
      const newIntent = await createPaymentIntent(cart.id);
      setIntent(newIntent);
      setStep('payment');
    } catch (e) {
      setError(e?.message || 'Could not start the payment. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  // Step 2 submit: confirm the payment, then advance the workflow
  // initial → checkout → confirmed (order-require-payment checks the charge).
  async function payAndPlaceOrder(card) {
    setError(null);
    setSubmitting(true);
    try {
      await confirmPayment(cart.id, card);

      await transition('order', cart.id, 'checkout');
      await transition('order', cart.id, 'confirmed');

      // Read back the placed order for the confirmation screen.
      const { data: placed } = await supabaseClient.from('order')
        .select('id, grand_total, subtotal, shipping_costs, discount_amount')
        .eq('id', cart.id).maybeSingle();
      onPlaced(placed ?? { id: cart.id, grand_total: subtotal + shippingCost });
    } catch (e) {
      setError(e?.message || 'Payment failed. Please try again.');
      // A failed confirm invalidates the intent; open a fresh one so retry works.
      try {
        const newIntent = await createPaymentIntent(cart.id);
        setIntent(newIntent);
      } catch {
        setStep('details');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Overlay onClose={submitting ? undefined : onClose} align="center">
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 'min(680px, 100%)', maxHeight: '92vh', overflowY: 'auto', background: '#fff',
        borderRadius: 18, boxShadow: '0 20px 60px rgba(15,23,42,0.25)',
      }}>
        <DrawerHeader title={step === 'payment' ? 'Payment' : 'Checkout'} onClose={submitting ? undefined : onClose} />
        <div style={{ padding: '4px 24px 24px' }}>
          {step === 'payment' ? (
            <PaymentPanel
              amount={intent?.amount ?? subtotal + shippingCost}
              error={error}
              submitting={submitting}
              onPay={payAndPlaceOrder}
              onBack={() => { setError(null); setStep('details'); }}
            />
          ) : (<>
          <SectionTitle>Shipping address</SectionTitle>
          {savedAddresses.length > 0 && (
            <select onChange={loadAddress} defaultValue="" style={{
              marginBottom: 12, width: '100%', padding: '10px 12px', borderRadius: 10,
              border: `1px solid ${BORDER}`, fontSize: 14, color: INK, fontFamily: FONT, background: '#fff',
            }}>
              <option value="">Load from saved address…</option>
              {savedAddresses.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="First name *" value={form.first_name} onChange={set('first_name')} />
            <Field label="Last name *" value={form.last_name} onChange={set('last_name')} />
            <Field label="Address *" value={form.street_line_1} onChange={set('street_line_1')} span />
            <Field label="Apartment, suite (optional)" value={form.street_line_2} onChange={set('street_line_2')} span />
            <ComboField label="City *" value={form.city} onChange={setAddr('city')} onClear={clearAddr('city')} {...addrOptions('city')} />
            <ComboField label="State / Province *" value={form.state_province} onChange={setAddr('state_province')} onClear={clearAddr('state_province')} {...addrOptions('state_province')} />
            <Field label="Postal code *" value={form.postal_code} onChange={set('postal_code')} />
            <ComboField label="Country *" value={form.country} onChange={setAddr('country')} onClear={clearAddr('country')} {...addrOptions('country')} />
          </div>
          {!addrValid && (
            <div style={{ marginTop: 8, color: '#b91c1c', fontSize: 13 }}>
              This country / state / city combination is not recognized.
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            {!saveOpen ? (
              <button type="button" disabled={!canSave} onClick={() => setSaveOpen(true)} style={{
                border: 'none', background: 'transparent', padding: 0, fontSize: 13, fontWeight: 600,
                color: canSave ? ACCENT : '#94a3b8', cursor: canSave ? 'pointer' : 'default',
              }}>+ Save as new address</button>
            ) : (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input value={saveName} onChange={(e) => setSaveName(e.target.value)} autoFocus
                  placeholder="Address name (e.g. Home)" style={{
                    flex: 1, padding: '9px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
                    fontSize: 14, color: INK, fontFamily: FONT,
                  }} />
                <button type="button" onClick={saveAddress} disabled={saving || !saveName.trim()} style={{
                  border: 'none', borderRadius: 10, padding: '9px 16px', fontWeight: 700, fontSize: 14,
                  color: '#fff', background: saving || !saveName.trim() ? '#cbd5e1' : ACCENT,
                  cursor: saving || !saveName.trim() ? 'default' : 'pointer',
                }}>{saving ? 'Saving…' : 'Save'}</button>
                <button type="button" onClick={() => { setSaveOpen(false); setSaveName(''); }} style={{
                  border: `1px solid ${BORDER}`, borderRadius: 10, padding: '9px 14px', fontSize: 14,
                  background: '#fff', color: MUTED, cursor: 'pointer',
                }}>Cancel</button>
              </div>
            )}
          </div>

          <SectionTitle>Shipping method</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {shippingMethods.map((m) => (
              <label key={m.id} style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
                border: `1px solid ${shippingId === m.id ? ACCENT : BORDER}`, borderRadius: 11,
                cursor: 'pointer', background: shippingId === m.id ? '#eef2ff' : '#fff',
              }}>
                <input type="radio" name="ship" checked={shippingId === m.id}
                  onChange={() => setShippingId(m.id)} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{m.name}</div>
                  <div style={{ color: MUTED, fontSize: 13 }}>
                    {m.carrier ? `${m.carrier} · ` : ''}
                    {m.estimated_days_min}-{m.estimated_days_max} business days
                  </div>
                </div>
                <strong>{Number(m.base_cost) === 0 ? 'Free' : money(m.base_cost)}</strong>
              </label>
            ))}
          </div>

          <SectionTitle>Discount code</SectionTitle>
          <Field label="Coupon (optional)" value={couponCode}
            onChange={(e) => setCouponCode(e.target.value)} placeholder="e.g. WELCOME10" />

          <SectionTitle>Order notes</SectionTitle>
          <Field label="Delivery instructions (optional)" value={notes}
            onChange={(e) => setNotes(e.target.value)} />

          <div style={{ marginTop: 22, padding: 16, background: BG_SOFT, borderRadius: 12 }}>
            <Row label="Subtotal" value={money(subtotal)} />
            <Row label="Shipping" value={shippingCost === 0 ? 'Free' : money(shippingCost)} />
            <div style={{ borderTop: `1px solid ${BORDER}`, margin: '8px 0' }} />
            <Row label="Total (before discount)" value={money(subtotal + shippingCost)} strong />
          </div>

          {error && (
            <div style={{ marginTop: 14, color: '#b91c1c', background: '#fef2f2',
              padding: '10px 14px', borderRadius: 10, fontSize: 14 }}>{error}</div>
          )}

          <button disabled={!valid || submitting} onClick={continueToPayment} style={{
            marginTop: 18, width: '100%', padding: '14px 0', border: 'none', borderRadius: 12,
            background: valid && !submitting ? ACCENT : '#cbd5e1', color: '#fff',
            fontWeight: 700, fontSize: 16, cursor: valid && !submitting ? 'pointer' : 'default',
          }}>
            {submitting ? 'Preparing payment…' : `Continue to payment · ${money(subtotal + shippingCost)}`}
          </button>
          </>)}
        </div>
      </div>
    </Overlay>
  );
}

// Card entry for the payment step. With paymentsDevMode the simulator is active:
// fields are prefilled with Stripe's success test card and no real charge happens.
function PaymentPanel({ amount, error, submitting, onPay, onBack }) {
  const [number, setNumber] = useState(paymentsDevMode ? '4242 4242 4242 4242' : '');
  const [expiry, setExpiry] = useState(paymentsDevMode ? '12/30' : '');
  const [cvc, setCvc] = useState(paymentsDevMode ? '123' : '');

  const digits = number.replace(/\D/g, '');
  const expiryMatch = expiry.match(/^\s*(\d{2})\s*\/\s*(\d{2}|\d{4})\s*$/);
  const cardValid = digits.length >= 12 && !!expiryMatch && /^\d{3,4}$/.test(cvc.trim());

  function pay() {
    if (!cardValid || submitting) return;
    onPay({
      number: digits,
      exp_month: Number(expiryMatch[1]),
      exp_year: Number(expiryMatch[2].length === 2 ? `20${expiryMatch[2]}` : expiryMatch[2]),
      cvc: cvc.trim(),
    });
  }

  return (
    <div>
      {paymentsDevMode && (
        <div style={{
          marginTop: 16, padding: '12px 14px', borderRadius: 10,
          background: '#fffbeb', color: '#92400e', fontSize: 13, lineHeight: 1.5,
        }}>
          <strong>Test mode</strong> — no real charge is made. Card 4242 4242 4242 4242
          succeeds; 4000 0000 0000 0002 is declined.
        </div>
      )}

      <SectionTitle>Card details</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Card number *" value={number} onChange={(e) => setNumber(e.target.value)}
          placeholder="1234 5678 9012 3456" span />
        <Field label="Expiry (MM/YY) *" value={expiry} onChange={(e) => setExpiry(e.target.value)}
          placeholder="12/30" />
        <Field label="CVC *" value={cvc} onChange={(e) => setCvc(e.target.value)} placeholder="123" />
      </div>

      <div style={{ marginTop: 22, padding: 16, background: BG_SOFT, borderRadius: 12 }}>
        <Row label="Total to pay" value={money(amount)} strong />
      </div>

      {error && (
        <div style={{ marginTop: 14, color: '#b91c1c', background: '#fef2f2',
          padding: '10px 14px', borderRadius: 10, fontSize: 14 }}>{error}</div>
      )}

      <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
        <button type="button" onClick={onBack} disabled={submitting} style={{
          flex: 1, padding: '14px 0', borderRadius: 12, border: `1px solid ${BORDER}`,
          background: '#fff', color: INK, fontWeight: 700, fontSize: 15,
          cursor: submitting ? 'default' : 'pointer',
        }}>Back</button>
        <button type="button" onClick={pay} disabled={!cardValid || submitting} style={{
          flex: 2, padding: '14px 0', border: 'none', borderRadius: 12,
          background: cardValid && !submitting ? ACCENT : '#cbd5e1', color: '#fff',
          fontWeight: 700, fontSize: 16, cursor: cardValid && !submitting ? 'pointer' : 'default',
        }}>
          {submitting ? 'Processing…' : `Pay ${money(amount)}`}
        </button>
      </div>
    </div>
  );
}

function ConfirmationOverlay({ order, onClose }) {
  return (
    <Overlay onClose={onClose} align="center">
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 'min(460px, 100%)', background: '#fff', borderRadius: 18, padding: 32,
        textAlign: 'center', boxShadow: '0 20px 60px rgba(15,23,42,0.25)',
      }}>
        <div style={{
          width: 64, height: 64, borderRadius: '50%', margin: '0 auto 16px',
          background: '#dcfce7', color: '#16a34a', fontSize: 34,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>✓</div>
        <h2 style={{ margin: '0 0 6px', fontSize: 24 }}>Order placed!</h2>
        <p style={{ margin: '0 0 20px', color: MUTED }}>
          Thank you — your order <strong>#{order.id}</strong> has been confirmed.
        </p>
        {order.grand_total != null && (
          <div style={{ padding: 16, background: BG_SOFT, borderRadius: 12, marginBottom: 20, textAlign: 'left' }}>
            {order.subtotal != null && <Row label="Subtotal" value={money(order.subtotal)} />}
            {order.discount_amount != null && Number(order.discount_amount) > 0 &&
              <Row label="Discount" value={`− ${money(order.discount_amount)}`} />}
            {order.shipping_costs != null && <Row label="Shipping" value={money(order.shipping_costs)} />}
            <div style={{ borderTop: `1px solid ${BORDER}`, margin: '8px 0' }} />
            <Row label="Total paid" value={money(order.grand_total)} strong />
          </div>
        )}
        <button onClick={onClose} style={{
          width: '100%', padding: '13px 0', border: 'none', borderRadius: 11,
          background: ACCENT, color: '#fff', fontWeight: 700, fontSize: 15, cursor: 'pointer',
        }}>Continue shopping</button>
      </div>
    </Overlay>
  );
}

// ===========================================================================
// Shared primitives
// ===========================================================================

function Overlay({ children, onClose, align }) {
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(15,23,42,0.45)',
      display: 'flex', justifyContent: align === 'flex-end' ? 'flex-end' : 'center',
      alignItems: align === 'center' ? 'center' : 'stretch',
      padding: align === 'center' ? 16 : 0,
    }}>{children}</div>
  );
}

function DrawerHeader({ title, onClose }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '18px 24px', borderBottom: `1px solid ${BORDER}`,
    }}>
      <h2 style={{ margin: 0, fontSize: 19 }}>{title}</h2>
      {onClose && (
        <button onClick={onClose} style={{
          border: 'none', background: 'transparent', fontSize: 22, cursor: 'pointer', color: MUTED, lineHeight: 1,
        }}>×</button>
      )}
    </div>
  );
}

export function SectionTitle({ children }) {
  return <div style={{ fontWeight: 700, fontSize: 15, margin: '22px 0 12px' }}>{children}</div>;
}

export function Field({ label, value, onChange, span, placeholder, suggestions }) {
  const listId = suggestions ? `dl-${label.replace(/\W+/g, '-')}` : undefined;
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5, gridColumn: span ? '1 / -1' : 'auto' }}>
      <span style={{ fontSize: 12.5, color: MUTED, fontWeight: 600 }}>{label}</span>
      <input value={value} onChange={onChange} placeholder={placeholder} list={listId} style={{
        padding: '10px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
        fontSize: 14, color: INK, fontFamily: FONT,
      }} />
      {suggestions && (
        <datalist id={listId}>
          {suggestions.map((opt) => <option key={opt} value={opt} />)}
        </datalist>
      )}
    </label>
  );
}

// Combo input for the cascading address fields: a clickable dropdown of the
// compatible options (from the address validation) that also accepts free entry
// when the validation allows it. Clearing wipes the dependent cascade fields.
export function ComboField({ label, value, options, allowFree, onChange, onClear, span }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(null); // null → show committed value
  const ref = useRef(null);
  const text = query ?? value ?? '';
  const lower = text.toLowerCase();
  const filtered = options.filter((o) => o.toLowerCase().includes(lower));
  const list = filtered.length ? filtered : options;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setQuery(null); }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const choose = (opt) => { onChange(opt); setQuery(null); setOpen(false); };

  return (
    <div ref={ref} style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 5, gridColumn: span ? '1 / -1' : 'auto' }}>
      <span style={{ fontSize: 12.5, color: MUTED, fontWeight: 600 }}>{label}</span>
      <div style={{ position: 'relative' }}>
        <input
          value={text}
          placeholder="Select or type…"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setOpen(true);
            if (allowFree) { setQuery(null); onChange(e.target.value); }
            else setQuery(e.target.value);
          }}
          style={{
            width: '100%', boxSizing: 'border-box', padding: '10px 30px 10px 12px',
            borderRadius: 10, border: `1px solid ${BORDER}`, fontSize: 14, color: INK, fontFamily: FONT,
          }}
        />
        {value ? (
          <button type="button" aria-label="Clear" onMouseDown={(e) => { e.preventDefault(); onClear(); setQuery(null); setOpen(false); }}
            style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'transparent', cursor: 'pointer', color: MUTED, fontSize: 18, lineHeight: 1 }}>×</button>
        ) : (
          <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: MUTED, fontSize: 11, pointerEvents: 'none' }}>▾</span>
        )}
        {open && list.length > 0 && (
          <ul style={{
            position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 60, margin: 0,
            padding: 4, listStyle: 'none', background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 10,
            maxHeight: 220, overflowY: 'auto', boxShadow: '0 12px 30px rgba(15,23,42,0.18)',
          }}>
            {list.map((opt) => (
              <li key={opt} onMouseDown={(e) => { e.preventDefault(); choose(opt); }} style={{
                padding: '8px 12px', borderRadius: 7, cursor: 'pointer', fontSize: 14, color: INK,
                background: opt === value ? '#eef2ff' : 'transparent',
              }}>{opt}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, strong }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 14 }}>
      <span style={{ color: strong ? INK : MUTED, fontWeight: strong ? 700 : 400 }}>{label}</span>
      <span style={{ fontWeight: strong ? 800 : 600 }}>{value}</span>
    </div>
  );
}

function Centered({ children }) {
  return (
    <div style={{ textAlign: 'center', color: MUTED, padding: '80px 0', fontSize: 15 }}>{children}</div>
  );
}

const linkStyle = { textDecoration: 'none', color: INK, fontSize: 14, fontWeight: 600 };
const menuItemStyle = { ...linkStyle, padding: '8px 12px', borderRadius: 7 };
const primaryLink = { background: ACCENT, color: '#fff', padding: '8px 16px', borderRadius: 9 };
const cartButtonStyle = {
  position: 'relative', border: `1px solid ${BORDER}`, background: '#fff', borderRadius: 11,
  width: 42, height: 42, cursor: 'pointer', fontSize: 18,
};
const cartBadgeStyle = {
  position: 'absolute', top: -6, right: -6, background: ACCENT, color: '#fff',
  borderRadius: 999, minWidth: 20, height: 20, fontSize: 12, fontWeight: 700,
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 5px',
};
