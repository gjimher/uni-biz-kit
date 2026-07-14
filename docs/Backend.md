# Backend

UniBizKit generates a complete **Supabase (PostgreSQL)** backend from the model. All security and business-rule enforcement lives here: the [frontend](Frontend.md) is untrusted and the database only accepts what the policies, triggers and edge functions allow.

## Backend Model Files

The backend-relevant part of an application model (see `models/test-app`,
`models/b2c-app`) consists of JSON files—with comments, hence the `.jsonc`
extension (see [Model.md](Model.md#model-files))—each validated against its
meta-schema in `schemas/`:

| File | Defines | Docs |
|------|---------|------|
| `concepts.jsonc` | Entities, fields, relationships | this page |
| `security.jsonc` | Roles, users, access rules, SSO | [Security.md](Security.md) |
| `rules.jsonc` | Server-side business rules (FEEL) | this page |
| `integrations.jsonc` | External replication and FEEL mappings | [Integrations.md](Integrations.md) |
| `backend/actions/*.js` | Authenticated concept actions | [Action functions](#action-functions) |
| `deployed_data.jsonc` | Rows synchronized on every deployment | this page |
| `workflow.jsonc` | State machines per concept | [Workflow.md](Workflow.md) |
| `seed_data.jsonc` | Initial records | this page |
| `system.jsonc` | Runtime services such as SMTP and payments | [Deployment.md](Deployment.md#runtime-configuration-systemjsonc) |
| `deployment.jsonc` | Development and production deployment | [Deployment.md](Deployment.md#configuration-deploymentjsonc) |
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

An optional `relation_to_one` can set `on_delete` to `snapshot_data`. Before the
referenced row is deleted, its complete JSON representation is stored in the
internal `_<field>_deleted_snapshot` column. PostgreSQL then applies `ON DELETE
SET NULL` to the foreign key. The generated UI continues linking to a live
record and, after deletion, opens the stored snapshot in a dialog instead.

`relation_to_many` generates a join table. `prefill` copies values from a related sub-collection into the record inline: the user picks one related record (e.g. one of the customer's saved addresses) and its fields are expanded onto this concept (`shipping_address_street`, `shipping_address_city`, …). `markdown` is long-form text stored as `TEXT` and edited in the UI with a markdown editor (source + live preview).

Some types accept a `subtype` refining rendering/storage — e.g. `decimal` with `subtype: "money"` renders as currency in the UI.

### Field properties

`required`, `unique`, `default`, `min`/`max`, `min_length`/`max_length`, `precision`/`scale`, `enum_values`, `size` (UI hint: `s`/`m`/`l`), `calculated` (see [Calculated fields](#calculated-fields)) and `description`. For `decimal`, `precision` is the total number of digits and `scale` the fractional digits. For `datetime`, `precision` is `"minute"` (the default) or `"second"`; it controls list/show formatting and the input step.

Constraints are enforced in the database (`NOT NULL`, `UNIQUE`, `CHECK`) and mirrored as form validation in the UI.

Profile concepts support two extra forms (see [Security.md](Security.md#mandatory-profile-fields) and the property descriptions in `schemas/concepts_schema.json`): `"required": "ask_after_login"` keeps the column nullable but makes the UI collect the value right after login, and `"default": "from_metadata(key, ...)"` fills the field from the auth token's user metadata when the profile row is created.

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

Each rule compiles to its own [backend function](#backend-functions), so it runs server-side and cannot be bypassed by the frontend.

## Seed Data (`seed_data.jsonc`)

`seed_data.jsonc` supplies the initial records grouped by concept under `records`.
`include_test_data` controls whether the generator also creates deterministic
sample rows. Document fields, such as product images, can be embedded as base64;
the reset process uploads them to the generated Storage buckets.

Seed data is loaded when a development database is reset and when a fresh
production database is provisioned. It is initialization data, not an
authoritative set: later deployments do not reconcile rows that users have
changed or removed.

## Deployed Data (`deployed_data.jsonc`)

Deployed data declares model-owned records that are reconciled on every
development reset and production deployment:

```jsonc
{
  "$schema": "../../schemas/deployed_data_schema.json",
  "concepts": [{
    "concept": "currency",
    "on_removed": "ignore",
    "records": [
      { "code": "EUR", "name": "Euro", "active": true }
    ]
  }]
}
```

The upsert key comes from the concept's local stored
`id_presentation.fields`; related presentation paths are ignored. Every record
must provide each key field. Generated fields and to-many relations cannot be
assigned.

`on_removed` controls rows whose key exists in the database but is absent from
the authoritative `records` array:

* `"ignore"` leaves those rows unchanged and is the default.
* `"delete"` deletes them, subject to foreign keys and cascades.

An empty `records` array applies the removal policy to every existing row. The
whole operation is transactional: validation, upserts and removals either all
succeed or none are committed.

The generator writes the merged model and framework-owned entries to
`deployed_data_extended.json`. For example, `_integration` uses `"delete"`, so
removing an integration definition also removes its run history through the
generated cascade. The shared `backend/deployed_data_runtime.py` applies this
data both from local resets and from the production provisioner.

During development, apply the generated file or an alternative JSON/JSONC file
with:

```bash
python bin/dev-deploy-data.py
python bin/dev-deploy-data.py /tmp/alternative-deployed-data.jsonc
```

The command reports inserted, updated and removed rows for each concept.

## Backend Functions

Backend functions, implemented as Supabase Edge Functions, are Deno functions deployed inside the app's Supabase instance. They are the trusted place for business logic that goes beyond what SQL constraints and RLS can express — the frontend calls them, it never implements them. Generated functions:

* **`workflow-transition`** — applies a state change to a record: checks the caller's role owns the current state, runs the `check`/`update` rules bound to the transition, and records the history. See [Workflow.md](Workflow.md).
* **One function per rule** in `rules.jsonc` (e.g. `order-compute-totals`, `order-require-payment`), invoked by `workflow-transition` or directly.
* **`payment`** — Stripe proxy (or dev simulator) charging the configured amount field, generated when `system.jsonc` enables payments.

Edge functions are also the intended mechanism for **integration between models**: business APIs that call each other across applications (see [Architecture.md](Architecture.md#integration-between-models)).

The generated `integration-run` function executes scheduled and manual external replication; see [Integrations](Integrations.md).

Concept actions use the same generated backend runtime without exposing its provider-specific details in the model; see [Action functions](#action-functions).

For manual testing, `bin/dev-supabase-call-edge-function.py` calls a function authenticated as a given user (see [Development.md](Development.md)).

## Dependencies

Keep external dependencies and their exact versions explicit in the source:

```js
import slugify from "npm:slugify@1.6.6";
import path from "jsr:@std/path@1.0.8";
```

`prod-dc-publish.py` builds the functions image through a Deno stage that resolves every generated entrypoint. It then repeats dependency installation with `--cached-only` and copies the complete `DENO_DIR` into the final Edge Runtime image. A missing package fails publication; a published image can load its dependency graph without npm, JSR or another module registry being available. Imports assembled dynamically from runtime strings cannot be discovered and are not supported.

### Action functions

Concept actions expose trusted JavaScript as standard buttons in generated list, edit or show views. Put the module in `backend/actions/` beside `concepts.jsonc` and declare only its file name on the concept:

```jsonc
"actions": [{
  "label": "Recalculate",
  "source": "recalculate.js",
  "placement": ["list", "edit"]
}]
```

The file name becomes the generated function endpoint. The module exports one function:

```js
export async function run({ id, ids, supabase, serviceClient, user }) {
  return { status: "ok", message: `Updated ${ids.length} records` };
}
```

`id` is set for a single selected record and `ids` always contains the selection. `supabase` preserves the caller's row-level security; `serviceClient` is privileged and must be used deliberately. `user` is the authenticated Supabase user.

The result is `{ status: "ok" | "ko", message?: string }`. The UI supplies a generic success or error notification when `message` is absent, otherwise it displays the returned message. Thrown errors become `ko` responses. A list action is disabled until at least one row is selected.

List actions appear in the bulk-selection toolbar beside Delete and receive every selected id. Edit actions appear in the upper action bar before Show, so they remain accessible independently of the form length.

Sources whose file name begins with `_` are reserved for framework-injected actions. The current backend generates authenticated Supabase Edge Function wrappers as an implementation detail.
