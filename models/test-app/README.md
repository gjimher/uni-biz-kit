# Test App — Reference Model

A B2C e-commerce example that exercises all major UniBizKit features. It serves as both a learning reference and the integration test input (`pytest` reads from this directory).

## Domain

A simple online store with six concepts:

| Concept | Description |
|---------|-------------|
| `product` | Catalog items with SKU, stock, pricing, versioned documents, and a status lifecycle |
| `category` | Hierarchical (self-referencing parent/child) classification |
| `customer` | Registered user profiles linked to the `user` role |
| `address` | Per-customer saved addresses (part-of relationship, cascading delete) |
| `order` | Customer purchases governed by a state machine |
| `order_item` | Line items linking an order to a product |

## Files

| File | Purpose |
|------|---------|
| `concepts.jsonc` | Business entities, fields, relationships, and calculated values |
| `presentation.jsonc` | Navigation menu and list-view field visibility rules |
| `security.jsonc` | Roles, seed users, and per-field access control rules |
| `workflow.jsonc` | State machine definitions (order lifecycle) |
| `rules.jsonc` | Business rules evaluated by the FEEL expression engine |
| `seed_data.jsonc` | Mandatory records loaded at every deploy |
| `system.jsonc` | Infrastructure settings (SMTP) |
| `deployment.jsonc` | Deployment parameters (`base_uri`) |
| `validations/address.csv` | CSV-driven cascading validation for `country → province → city` |
| `presentation/` | Custom pages (MDX/JSX), layouts, and static assets |

## Key patterns demonstrated

### Calculated fields

The `calculated` attribute on a field tells the generator how the value is produced rather than entered manually. Available strategies:

| Expression | Meaning |
|-----------|---------|
| `"\"_user_email\""` | Binds to the authenticated user's email (string literal referencing an internal variable) |
| `copy_logged_on_insert(customer)` | Sets the relation to the logged-in user's linked profile record on insert |
| `rollup(sum, order_item, total_price)` | Aggregates a child concept's numeric field (sum, min, max, count) |
| `copy(product, price, on_change_in_state_initial)` | Copies a field from a related record, only while the parent is in a given state |
| `quantity*unit_price` | Inline arithmetic evaluated on every change |
| `by_rules` | Value is computed by a named rule in `rules.jsonc` |

### Relationship subtypes

| Type | Subtype | Behaviour |
|------|---------|-----------|
| `relation_to_one` | `part_of` | Child record — delete cascades to parent (address → customer, order_item → order) |
| `relation_to_one` | `related_to` | Loose foreign key — no cascade (order → customer, order_item → product) |
| `relation_to_many` | — | Many-to-many join table (product ↔ category) |
| `prefill` | `customer.addresses` | Expands a sub-collection's fields inline at the parent level (shipping/billing address on order) |

### Hierarchical `id_presentation`

`category` uses `"fields": ["parent.id_presentation", "name"]` with separator `/`. This traverses the parent's own display label recursively, producing labels like `Electronics / Keyboards` in lists and selectors.

### Security layers

- **Level 2 (`rules_level_2`)** — per-role, per-concept field access. Access values: `read`, `write`, `owner_write` (write only own records).
- **Level 3 (`rules_level_3`)** — glob-pattern field rules applied after level 2. `admin_*` fields are read-only for the `user` role regardless of concept.
- `_anon` is a built-in role for unauthenticated access (mapped to Supabase's `anon` key).
- `profile_concept: "customer"` links the `user` role to a customer record, enabling ownership checks.

The `list_field_rules_level_2` block in `presentation.jsonc` uses a compact DSL to control which fields appear in list views:

| Token | Meaning |
|-------|---------|
| `!field` | Hide field from lists entirely |
| `!>field` | Promote field to the start of the list |
| `id_presentation[0]` | Insert the first element of the concept's `id_presentation` |

### Workflow (state machine)

`order_workflow` defines five states: `initial → ordered → accepted → sent → delivered`. Each state's `owners` list specifies which roles may act on records in that state (i.e., trigger a transition into it).

### Business rules (FEEL engine)

`rules.jsonc` uses FEEL (Friendly Enough Expression Language) expressions. Three action types:

| Action | Behaviour |
|--------|-----------|
| `update` | Write computed values back to the record |
| `check` | Validate; returning an error object aborts the state transition |
| `return` | Expose a computed value to the frontend without a DB write |

Rules fire **synchronously** (`when`) before/after a state change, or **asynchronously** in the background (`when_async`) without blocking the user.

### CSV-driven cascading validation

`validations/address.csv` drives cascading dropdowns for `country → province → city` on the `address` concept. A `*` in a column means "any value is valid at this level given the parent selection". The final row `*,*,*` is the catch-all fallback.

### Custom pages

`presentation/pages/` contains MDX and JSX pages injected into the generated frontend:

- `index.mdx` — the home/dashboard page
- `example-mdx.mdx` — dynamic MDX using `props.model` to render model metadata
- `example-data.jsx` — raw data fetching with `useGetList`
- `example-admin.jsx` — React-Admin `Datagrid` component usage

Pages under `priv/` are identical in content but wrapped with the `<Authenticated>` component, requiring login.
