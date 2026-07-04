# Frontend

UniBizKit generates a **React-Admin** application (Vite) that talks directly to the app's Supabase instance.

**This layer is untrusted and provides no security.** It runs in the user's browser with the public anon key; anything it hides can be bypassed with `curl`. All access control is enforced by the [backend](Backend.md) through RLS policies, triggers and edge functions — see [Security.md](Security.md). The UI only *mirrors* those permissions for usability (hiding fields the role cannot read, disabling forms it cannot write).

## Generated Output (`<app>/frontend/`)

```
frontend/
├── .env.development          # tokens file: links the app to its Supabase instance
├── vite.config.js            # base path + /api proxy
└── src/
    ├── App.jsx               # React-Admin app: one resource per concept
    ├── resources/            # generated List/Create/Edit/Show per concept
    ├── dataProvider.js       # Supabase data provider
    ├── authProvider.js       # Supabase auth (password + SSO)
    ├── supabaseClient.js     # single shared Supabase client
    └── presentation/         # custom pages (copied from the model) + router
```

### The tokens file and the `/api` proxy

`.env.development` links the frontend to its Supabase instance:

```bash
VITE_SUPABASE_URL=/b2c/api    # relative: resolved against the page origin
VITE_SUPABASE_KEY=<anon key>  # public, low-privilege key
```

`VITE_SUPABASE_URL` is a **relative** path. The Vite dev server (and `vite preview`) proxies `/<base>/api` → the app's Supabase API (Kong), so the frontend and the API stay same-origin and each application routes to **its own** Supabase instance via its `base_uri` (e.g. `/b2c/api` → b2c-app's Supabase). Ports and proxy details in [Development.md](Development.md).

## Generated Admin UI

For every concept: List, Create, Edit and Show views with field components chosen by type, form validation mirroring the model constraints, relationship handling, document attachments, and the [workflow selector](Workflow.md) on concepts with a workflow.

Configuration in `presentation.jsonc`:

* `locale`, `number_locale`, `currency` — UI language and number/currency formatting.
* `menu` — custom left menu; defaults to a flat list of all resources.
* `list_field_rules_level_1..3`, `list_sort` — which columns list views show and their default sort (higher levels override lower, same pattern as the [security rules](Security.md#how-rules-are-resolved)).
* `authenticated_pages` — which custom pages require login (see below).

## Custom Pages (MDX / JSX)

Files under the model's `presentation/pages/` are copied into `src/presentation/pages/` and routed **by file path**:

| File | Route |
|------|-------|
| `pages/index.mdx` | `/` |
| `pages/signin.jsx` | `/signin` |
| `pages/priv/orders.jsx` | `/priv/orders` |

* **MDX** — Markdown with JSX for content-centric pages; frontmatter can pick a layout (`layout: name` → `layouts/<name>.jsx`), and the generated `model` object is available for rendering data.
* **JSX** — full React components for tailored pages (storefront, checkout, account).

Pages matching an `authenticated_pages` pattern are wrapped in React-Admin's `<Authenticated>`; the rest are public and rely on [`_anon` read rules](Security.md#the-_anon-built-in-role) for their data. Custom pages use the same shared Supabase client and the CSV [validation helpers](Backend.md#validations-validationscsv) as the generated forms.

## The Recommended Split

A good compromise is to use the **generated admin UI to administer the data** and implement **a custom interface only for the end user**. That is what `models/b2c-app` does: customers get a tailored MDX/JSX storefront (catalog, cart, checkout, account) while staff manage products and orders in the generated React-Admin backoffice — both against the same backend, which enforces the same rules for both.
