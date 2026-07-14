# Integrations

UniBizKit can replicate external records into a local concept. A trusted JavaScript source handles the external protocol and pagination, FEEL adapts each object to the target schema, and the backend performs idempotent upserts.

## Model

Create `integrations.jsonc` beside `concepts.jsonc` and put connector modules in `backend/integrations/`:

```jsonc
{
  "$schema": "../../schemas/integrations_schema.json",
  "roles": ["operations", "admin"],
  "integrations": [{
    "name": "crm-accounts",
    "description": "Replicate CRM accounts",
    "target_concept": "company",
    "source": "crm-accounts.js",
    "schedule": "*/15 * * * *",
    "on_removed": { "set_false": "active" },
    "transform": "{ _external_id: input.accountId, name: input.legalName }"
  }]
}
```

The roles must exist in `security.jsonc`. They can inspect runs, edit notes, pause and invoke integrations. Backend authorization is enforced independently of the menu. `schedule` is an optional five-field UTC cron expression; without it the integration is manual only. `on_removed` defaults to `"ignore"`; `{ "set_false": "active" }` updates a boolean target field when the source explicitly reports that a record was removed.

## Identity and transformation

Every target concept receives an internal, unique `_external_id TEXT NOT NULL`. The FEEL transform must return a non-empty string `_external_id`; it is the upsert conflict key. Composite keys can be encoded by FEEL, for example `country + "|" + customerNumber`, when the source contract excludes the separator.

## Source module

The referenced JavaScript module exports:

```js
export async function fetchPage({ cursor, checkpoint, pageSize, config, secrets }) {
  return {
    items: [],
    removedExternalIds: [],
    nextCursor: null,
    complete: true,
    checkpoint,
  };
}
```

`cursor` is temporary pagination state within one run. `checkpoint` is durable and advances only after every page succeeds. `removedExternalIds` is optional and contains the external IDs of explicit source tombstones or removal events; it is not inferred from records absent in an incremental query. Values must be non-empty strings. The trusted module may implement HTTP, GraphQL, LDAP or another protocol and can read Edge Function environment variables through `Deno.env` or `secrets`.

`on_removed: "ignore"` consumes those events without changing target rows. `on_removed: { "set_false": "field" }` sets the selected boolean field to false for matching `_external_id` values. Successfully affected rows are recorded in `removed_count` and `last_removed_count`. True absence reconciliation requires a complete source snapshot and is intentionally separate from incremental removal events.

## Runtime and operations

`_integration` stores a read-only projection of each model definition—including `on_removed`—plus checkpoint, lease, notes, operational status and latest result. The source of truth remains `integrations.jsonc`; the runtime behavior is compiled into the deployed function, while the projection makes it visible in the UI. `operational_status` is `active` or `paused`; a paused integration keeps its cron job but scheduled and manual attempts are skipped. `_integration_run` stores each scheduled or manual attempt with timestamps, counters, checkpoints and errors; source payloads are not logged. Both are injected as regular concepts into `concepts_extended.json`, so their tables and React-Admin resources use the standard generators. Their generated field-level permissions are visible in `security_extended.json`.

`pg_cron` schedules calls and `pg_net` invokes the generated `integration-run` Edge Function. An expiring lease prevents overlaps. Integration definitions are injected into `deployed_data_extended.json` with `on_removed: "delete"`; removing a definition deletes its notes, checkpoint and run history.

Every development reset and production deployment reconciles scheduling after deployed data and the scheduler token are ready. The reconciler removes all known `_integration_*` jobs and recreates the jobs for rows with a non-empty schedule. This makes schedule changes and removals idempotent and independent of Git-tag schema migrations. Paused integrations remain scheduled, but the function records each attempt as skipped without reading the source.

Authorized users see **Operations → Integrations** and **Operations → Integration runs**. Integrations open directly in the standard edit form. **Run now** and **Reset checkpoint** are injected generic [backend actions](Backend.md#action-functions), rather than integration-specific frontend code. Resetting a checkpoint does not run the integration: it makes the next execution pass `checkpoint: null` to the source module, requesting a complete read. The action uses the integration lease and refuses to reset an integration that is already running. Runs have their own date-ordered list with filters for integration, status, trigger and requested date, plus a detailed checkpoint/error view.

## Secrets

Connector credentials are ordinary backend secrets: they need no declaration
in `integrations.jsonc` and are available through both `Deno.env` and the source
module's `secrets` argument. See [Secrets.md](Secrets.md) for development and
production management.

## Development mock

`python bin/dev-integration-odata-mock.py` starts a deterministic OData-like source with paginated `GET /odata/v4/Accounts` and `modifiedOn` filtering. The same command controls an existing process:

```bash
python bin/dev-integration-odata-mock.py --terminate
python bin/dev-integration-odata-mock.py --reset
python bin/dev-integration-odata-mock.py --advance
```

The shutdown endpoint only accepts loopback clients. GET requests never mutate data. The fourth deterministic change emits an OData tombstone for the initially active `PT|2001` account; the example integration maps it through `on_removed` and sets `external_company.active` to false. Later advances add deterministic demo companies indefinitely.

Invoke the first generated integration as an authenticated operator:

```bash
python bin/dev-supabase-call-edge-function.py admin@test.com integration-run '{"id": 1}'
python bin/dev-supabase-call-edge-function.py admin@test.com integration-reset-checkpoint '{"id": 1}'
```
