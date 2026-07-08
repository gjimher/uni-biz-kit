# Backend

UniBizKit generates a complete **Supabase (PostgreSQL)** backend from the model. All security and business-rule enforcement lives here: the [frontend](Frontend.md) is untrusted and the database only accepts what the policies, triggers and edge functions allow.

## The Model Directory

An application model is a directory (see `models/test-app`, `models/b2c-app`) of JSON files — with comments, hence the `.jsonc` extension (see [Model.md](Model.md#model-files)) — each validated against its meta-schema in `schemas/`:

| File | Defines | Docs |
|------|---------|------|
| `concepts.jsonc` | Entities, fields, relationships | this page |
| `security.jsonc` | Roles, users, access rules, SSO | [Security.md](Security.md) |
| `rules.jsonc` | Server-side business rules (FEEL) | this page |
| `workflow.jsonc` | State machines per concept | [Workflow.md](Workflow.md) |
| `presentation.jsonc` + `presentation/` | UI configuration and custom pages | [Frontend.md](Frontend.md) |
| `seed_data.jsonc` | Initial records | this page |
| `system.jsonc` | SMTP, payments | this page |
| `deployment.jsonc` | Base URI | this page |
| `validations/*.csv` | Data-driven field validations | this page |

## Concepts

Each concept becomes a table plus its CRUD UI. Example (from `models/b2c-app/concepts.jsonc`):

```jsonc
{
  "name": "category",
  "plural_name": "categories",
  "description": "Hierarchical product categories",
  "id_presentation": { "fields": ["parent.id_presentation", "name"], "separator": " / " },
  "documents": { "enabled": true, "tags": ["img_s", "img_m"] },
  "fields": [
    { "name": "parent", "type": "relation_to_one", "subtype": "part_of", "target": "category" },
    { "name": "name", "type": "string", "required": true, "unique": true, "max_length": 80 },
    {
      "name": "slug", "type": "string", "unique": true,
      // Read-only in the UI, computed by PostgreSQL (GENERATED ALWAYS AS)
      "calculated": "lower(regexp_replace(name, '[[:space:]]+', '-', 'g'))"
    },
    { "name": "is_active", "type": "boolean", "default": true }
  ]
}
```

### Concept properties

* `id_presentation` — how records are labelled and referenced across the UI (see [Frontend.md](Frontend.md#record-labels-id_presentation)).
* `documents` — enables file/image attachments per record, stored in Supabase Storage buckets. `tags` names the attachment slots; `versioned: true` keeps historical versions per tag instead of replacing them.
* `checks` — SQL check constraints at concept level.
* `data_size` — expected volume hint.

### Field types

`string`, `markdown`, `integer`, `decimal`, `enum`, `boolean`, `date`, `datetime`, `relation_to_one`, `relation_to_many`, `prefill`.

Relations declare their `target` concept. A `relation_to_one` also declares a `subtype`:

* `part_of` — ownership: the child belongs to the parent and deleting the parent **cascades** to the children (e.g. `order_item` part_of `order`, `address` part_of `customer`). A self-referential `part_of` (target = own concept) models a tree.
* `related_to` — a loose foreign key: deleting the target does **not** cascade (e.g. `order` related_to `customer`).

`relation_to_many` generates a join table. `prefill` copies values from a related sub-collection into the record inline: the user picks one related record (e.g. one of the customer's saved addresses) and its fields are expanded onto this concept (`shipping_address_street`, `shipping_address_city`, …). `markdown` is long-form text stored as `TEXT` and edited in the UI with a markdown editor (source + live preview).

Some types accept a `subtype` refining rendering/storage — e.g. `decimal` with `subtype: "money"` renders as currency in the UI.

### Field properties

`required`, `unique`, `default`, `min`/`max`, `min_length`/`max_length`, `precision`/`scale` (decimal), `enum_values`, `size` (UI hint: `s`/`m`/`l`), `calculated` (see [Calculated fields](#calculated-fields)) and `description`.

Constraints are enforced in the database (`NOT NULL`, `UNIQUE`, `CHECK`) and mirrored as form validation in the UI.

Field names starting with `_` are reserved for internals (see [Security.md](Security.md#internal-columns)).

### Calculated fields

A `calculated` field is read-only in the UI; its value is produced by one of these strategies instead of being entered:

| Strategy | Produces | Example |
|----------|----------|---------|
| SQL expression | A `GENERATED ALWAYS AS (...) STORED` column over the row's own columns | `quantity*unit_price` |
| `rollup(func, child_concept, child_field)` | An aggregate (`func` = `sum`/`count`/`avg`/`min`/`max`) of `child_field` over the child records `part_of` this concept, kept in sync by triggers | `rollup(sum,order_item,total_price)` |
| `copy(fk_field, source_field, when)` | A snapshot of `source_field` from the record the relation `fk_field` points to, taken when `when` fires: `on_insert`, `on_change`, or `on_change_in_state_<state>` (copy while in / on reaching that state, then freeze); join several with `+` | `copy(product,price,on_change_in_state_initial)` |
| `copy_logged_on_insert(fk_field)` | On insert, sets the relation `fk_field` to the logged-in user's linked [profile](Security.md#profile-concepts) record, then locks it | `copy_logged_on_insert(customer)` |
| `by_rules` | The field is written by the [business rule](#business-rules-rulesjsonc) whose `update` action targets it — a FEEL rule that runs in an edge function, sees the whole record, and computes what SQL cannot | `order.shipping_costs` from the order total |

A SQL expression is any PostgreSQL expression, so it can also reference a column by quoted identifier — including the internal columns injected on [profile concepts](Security.md#profile-concepts). The `customer.email` field uses `"_user_email"` to expose the logged-in user's auth email as a read-only column.

## Validations (`validations/*.csv`)

CSV files define valid combinations of related field values (e.g. `address.csv`: country → state/province → city). The rows are compiled into shared validation helpers used both by the generated forms and by custom pages. `*` acts as a wildcard.

## Business Rules (`rules.jsonc`)

Server-side business logic written in **FEEL** (Friendly Enough Expression Language) — a business-oriented language, not a programming language. Each rule declares:

* `concept` — the record the rule runs against.
* `feel_expr` — the expression. Context: `db.<concept>` (current record, related records via paths) and `auth.<concept>` (the logged-in user's [profile](Security.md#profile-concepts)).
* `action` — `update` writes the result back to the concept's fields; `check` validates and aborts the transition with `{ error: "..." }`; `return` exposes a computed value to the frontend without any DB write (a concept-less rule is a standalone function the frontend can call).
* `when` — fires **synchronously**, blocking until complete: `on_state_changed_to_<state>` (a workflow transition) or `on_change_in_state_<state>` (any edit while in a state).
* `when_async` — the same events, but fired **asynchronously** in the background so the user is not blocked (e.g. recomputing totals while a cart is edited).

Example (from `models/b2c-app/rules.jsonc`):

```jsonc
{
  "concept": "order",
  "name": "order-require-payment",
  "feel_expr": "if db.order.payment_status = \"paid\" then true else { error: \"The order must be paid before it can be confirmed\" }",
  "action": "check",
  "when": ["on_state_changed_to_confirmed"]
}
```

Each rule compiles to its own [edge function](#edge-functions), so it runs server-side and cannot be bypassed by the frontend.

## Seed Data (`seed_data.jsonc`)

Initial records per concept (`records`), plus `include_test_data` to toggle generated sample data. Document fields (e.g. product images) can be embedded base64; the reset script uploads them to the storage buckets.

## System (`system.jsonc`)

* `smtp` — mail server used for auth emails (in dev, the [SMTP mock](Development.md) prints them to stdout).
* `payments` — enables the `payment` edge function (Stripe proxy). `dev_mode: true` uses a built-in simulator, no Stripe credentials needed.

## Deployment (`deployment.jsonc`)

* `base_uri` — path prefix the app is served under (e.g. `/b2c`). Drives the frontend base path and the `/<base>/api` proxy (see [Frontend.md](Frontend.md)).

## Generated Output (`<app>/backend/`)

| Artifact | Contents |
|----------|----------|
| `supabase_schema.sql`, `supabase/migrations/` | Tables, constraints, RLS policies, triggers, auth hooks |
| `supabase/seed.sql`, `supabase_seed_data_dev.sql` | Seed data |
| `supabase/functions/` | Edge functions |
| `supabase/config.toml`, `supabase_config_dev.toml` | Supabase instance configuration (ports, auth, SMTP) |

Each application gets its **own Supabase instance**, in dev and in production (see [Architecture.md](Architecture.md)).

## Edge Functions

Edge functions are Deno functions deployed inside the app's Supabase instance. They are the trusted place for business logic that goes beyond what SQL constraints and RLS can express — the frontend calls them, it never implements them. Generated functions:

* **`workflow-transition`** — applies a state change to a record: checks the caller's role owns the current state, runs the `check`/`update` rules bound to the transition, and records the history. See [Workflow.md](Workflow.md).
* **One function per rule** in `rules.jsonc` (e.g. `order-compute-totals`, `order-require-payment`), invoked by `workflow-transition` or directly.
* **`payment`** — Stripe proxy (or dev simulator) charging the configured amount field, generated when `system.jsonc` enables payments.

Edge functions are also the intended mechanism for **integration between models**: business APIs that call each other across applications (see [Architecture.md](Architecture.md#integration-between-models)).

For manual testing, `bin/dev-supabase-call-edge-function.py` calls a function authenticated as a given user (see [Development.md](Development.md)).
