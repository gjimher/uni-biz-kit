# Frontend

UniBizKit generates a **React-Admin** application that talks directly to the app's Supabase instance.

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

For every concept: List, Create, Edit and Show views with field components chosen by type, form validation mirroring the model constraints, relationship handling, document attachments, and the [workflow selector](Workflow.md) on concepts with a workflow. List views additionally offer [configurable columns](#configurable-list-columns), [inline quick edit](#inline-quick-edit) and [CSV export/import](#csv-export-and-import).

### Record labels (`id_presentation`)

A concept's `id_presentation` (declared in `concepts.jsonc`) is the human-readable label used wherever a record is shown or referenced — list rows, selectors on related concepts, page titles. It takes:

* `fields` — the fields composing the label, joined by `separator`. A field can traverse a relation, including the target's own `id_presentation`: `category` uses `["parent.id_presentation", "name"]` with separator `/`, so the label is built **recursively** up the tree, producing `Electronics / Keyboards`.
* `separator` — the string placed between fields (e.g. `" / "`, `", "`).
* `show` — when `true`, the composed label is also rendered as its own column in list views (referenced as `id_presentation[0]` in the list rules below).

Configuration in `presentation.jsonc`:

* `locale`, `number_locale`, `currency` — UI language and number/currency formatting.
* `menu` — custom left menu; defaults to a flat list of all resources.
* `list_field_rules_level_1..3`, `list_sort` — which columns list views show and their default sort (see below).
* `authenticated_pages` — which custom pages require login (see below).

### List field rules

Each list view starts from a **pool** of candidate columns: `id_presentation` plus every model field, in model order (only `state_info`, the workflow history, is left out). The three rule levels `list_field_rules_level_1..3` transform that pool into the final column list. The levels run **one after another** — the result of one level is fed to the next, so a higher level refines what the lower ones left. The default level 1 is `*,!id_presentation,!_*`: add every field, then drop `id_presentation` and the internal `_`-prefixed metadata — so those are removed by the default *rule*, not hard-excluded from the pool.

Each level maps a concept to a rule string. The key can be the exact concept name, a `prefix*` pattern, or `*` as a fallback (most specific wins).

A rule string is a comma-separated list of tokens, applied left to right:

| Token | Effect |
|-------|--------|
| `field` | move/ensure `field` at the end |
| `*` | add every field in the pool |
| `prefix*` | add every field starting with `prefix` |
| `field[anchor]` | position `field`: **after** the `anchor` column, or at the **start** with `[0]` / the **end** with `[-1]` |
| `>field` / `>=field` | add the fields after / from `field` onward |
| `<field` / `<=field` | add the fields before / up to `field` |
| `!field` | hide `field` |
| `!prefix*` | hide every field starting with `prefix` |
| `!>field` / `!>=field` | hide the fields after / from `field` onward |
| `!<field` / `!<=field` | hide the fields before / up to `field` |

Examples from [`models/test-app/presentation.jsonc`](../models/test-app/presentation.jsonc) (level 2):

```jsonc
"list_field_rules_level_2": {
  // remove fields after price, add sku to the end, hide details
  //  (same as: "!*,name,description,details,price,sku")
  "product": "!>price, sku, !details",
  // hide slug (URL-only field, not useful in admin lists)
  "category": "!slug",
  // show id as the first column, remove fields after total_amount
  "order": "id_presentation[0], !>total_amount",
  // keep only up to the email column
  "customer": "!>email"
}
```

### List sort

`list_sort` sets the default ordering of a concept's list view — an object mapping each concept name to a `"<field> ASC|DESC"` string. Concepts without an entry keep React-Admin's default sort. Unlike the field rules, keys are exact concept names (no levels, no `*` patterns).

Example from [`models/test-app/presentation.jsonc`](../models/test-app/presentation.jsonc):

```jsonc
"list_sort": {
  // Newest orders first
  "order": "order_date DESC"
}
```

### Configurable list columns

List views open with the default columns computed by the field rules above, but the user can adjust them: the **Columns** button opens a panel to show or hide any non-internal field, and **Reset columns** returns to the defaults. The selection persists per concept in the browser's local storage (namespaced per app), so it survives reloads without affecting other users. The **Add filter** menu covers the same full field set, so any column a user adds can also be filtered on.

### Inline quick edit

The **Quick edit** button (shown to users with `write` access) opens the rows currently loaded in the list — same page, filters and sort — as an editable table in a fullscreen dialog, for spreadsheet-style editing of many records at once. The list does the navigating: filter and page there, quick-edit one page, save, move on.

* Each cell gets an editor for its field type: text (multiline for `size: l`), number, checkbox, date/datetime, enum select. Foreign keys use a preloaded select when the target concept's `data_size` is `s`, or a server-searched autocomplete for larger targets. Fields in a [CSV validation](Backend.md#validations-validationscsv) group use the same coherent autocomplete as the forms — picking `Bilbao` auto-fills `Bizkaia` and `Spain`. Calculated, prefill and workflow-state fields are shown read-only; markdown fields are edited in the forms only.
* Columns mirror the list view, including any the user added. Per-row buttons **duplicate** a row as a new record and **mark it for deletion** (undoable until saved). **Add row** creates records inline; required-for-create columns are added automatically if hidden. Concepts with required fields that cannot be filled inline (e.g. prefill addresses) do not offer row creation.
* **Copy/paste with a spreadsheet**, as headerless TSV so a column can be pasted over a different one: **Copy** puts the table on the clipboard as displayed (FKs as their `id_presentation`; the Id column — shown only when `id_presentation` is among the selected list columns — goes first); **Select** narrows Copy/Paste to chosen rows and columns; **Paste** fills the visible (or selected) cells positionally and **Paste insert** appends the clipboard as new rows. The clipboard shape must match the target (a grid one column wider drops its first column, assumed to be the Id). Pasted FK labels are resolved by `id_presentation`; unresolvable, ambiguous or unparsable cells are flagged in place and block only their own row.
* Changes are saved in one batch — updates (only the touched fields), inserts and deletes. Client-side validation (required fields and the validation groups actually touched) flags invalid rows without sending them; server rejections — row-level security, workflow-state triggers, unique/FK/check constraints — are reported per row with a readable message while the remaining rows still save. Rows whose workflow state is not owned by the user's roles are locked with the reason shown, and per-field permissions disable individual cells.

### CSV export and import

Every list view has **Export** and **Import** buttons (Import only for users with `write` access). Export downloads the currently filtered rows as a CSV that can be edited in a spreadsheet and imported back to insert and update records. A dialog lets you pick which columns to include.

The CSV format:

* `id_presentation` is the row key: **empty means insert, non-empty means update** of the matching record. It is recomputed by the database, so updating the fields it is built from changes it. The numeric `id` and calculated/internal fields are never exported or imported.
* Relation columns (both foreign keys and many-to-many) carry the target record's `id_presentation`. Many-to-many cells hold one value per line (newlines inside a quoted CSV cell).
* Document columns come in pairs per tag — `doc:<tag>:filename` and `doc:<tag>:content` (base64 data URI). Files over 1 MB are skipped on export with a warning and rejected on import; on versioned concepts import creates the next version.

Import first validates the whole file and reports **all** problems at once with their record number (the header is line 1): unknown columns, type errors, missing required values, unresolvable or ambiguous relation values, and update keys that match no record — or more than one, since `id_presentation` is not necessarily unique. If the file is clean, a summary (`X inserts, Y updates`) asks for confirmation before anything is written; execution then runs in chunks with a progress bar and lists any per-row failures at the end.

Update semantics: only the columns present in the file are written — an absent column leaves the field (or the many-to-many links) untouched, while a present-but-empty cell clears it. Imports run with the logged-in user's permissions, so row-level security applies as in the rest of the UI.

## Custom Pages (MDX / JSX)

Files under the model's `presentation/pages/` are copied into `src/presentation/pages/` and routed **by file path**:

| File | Route |
|------|-------|
| `pages/index.mdx` | `/` |
| `pages/signin.jsx` | `/signin` |
| `pages/priv/orders.jsx` | `/priv/orders` |

* **MDX** — Markdown with JSX for content-centric pages; frontmatter can pick a layout (`layout: name` → `layouts/<name>.jsx`), and the generated `model` object is available for rendering data.
* **JSX** — full React components for tailored pages (storefront, checkout, account).

Pages matching an `authenticated_pages` pattern are wrapped in a session guard built on the presentation lib: signed-out visitors are bounced to the app's `/signin` page and returned to the protected page after logging in (data is enforced server-side by RLS regardless). The rest are public and rely on [`_anon` read rules](Security.md#the-_anon-built-in-role) for their data. Custom pages use the same shared Supabase client and the CSV [validation helpers](Backend.md#validations-validationscsv) as the generated forms.

### Default Auth Pages & the Presentation Lib

Apps with `authentication_required` also get a set of default pages in `src/presentation/pages/` covering the account flows end to end: `signin.jsx`, `register.jsx` (when registration is allowed), `forgot-password.jsx`, `set-password.jsx` (the recovery-link landing), `change-password.jsx` and `complete-profile.jsx` (when a profile concept has `ask_after_login` fields). They are complete experiences — inline error/success messages, validation, redirects (including back to the page that required the login), test-user picker, SSO button when enabled — and they are the single implementation of those flows for the whole app: `signin.jsx` is also the `/login` route the admin backoffice redirects to, so overriding it rebrands every sign-in.

Their look & feel lives in one overridable module, `presentation/style/auth.jsx` (design tokens plus the `Card`/`Field`/`Message`/`SubmitButton` primitives): a model **rebrands every auth page at once** by providing its own `presentation/style/auth.jsx` with the same exports — the pages themselves stay generated and keep receiving generator improvements (that is what `models/b2c-app` and `models/intranet-app` do). For structural redesigns beyond what the primitives allow, copy the page into the model's `presentation/pages/` under the same name: the model copy replaces the generated default. Pages are built only on React, react-router and the shared helper lib, so they keep working across react-admin/MUI upgrades.

Registration stays minimal (email + password) on purpose: mandatory profile fields (`required: "ask_after_login"`) are collected by a single post-login gate. The presentation router redirects any session that still misses them to `/complete-profile` — however the session was established: password login, registration confirmation link or SSO — and the admin backoffice keeps its own blocking dialog.

The lib (`import { ... } from './presentation/lib'`, generated in `src/presentation/lib/`) wraps the Supabase client for custom pages: sessions (`useSession`, `useRequireSession`, `signIn`, `signUp`, `signOut`, `signInWithSso`), passwords (`changePassword`, `requestPasswordReset`, `completePasswordReset`), profiles (`useProfile`, `updateProfile`, `getMissingProfileFields`, `completeProfileFields`), plus formatting, storage, workflow and CSV-validation helpers — each documented where it is generated. The convention throughout: helpers return data and throw `Error` with a user-displayable message, and each page decides where to render it (inline alert, status bar, ...).

## The Recommended Split

A good compromise is to use the **generated admin UI to administer the data** and implement **a custom interface only for the end user**. That is what `models/b2c-app` does: customers get a tailored MDX/JSX storefront (catalog, cart, checkout, account) while staff manage products and orders in the generated React-Admin backoffice — both against the same backend, which enforces the same rules for both.
