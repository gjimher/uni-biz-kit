# The Model

UniBizKit is a **model-driven development** (MDD) tool: an application is not written, it is *described*. The model is the single source of truth — database schema, security policies, business logic and UI are all generated from it, so they can never drift apart.

This is what makes the approach safe for AI agents: an agent (or a functional user) produces a declarative model, and the generator turns it into a stack whose correctness and security do not depend on the quality of hand-written code. See [Architecture.md](Architecture.md#change-levels) for the levels at which changes can be made.

## Model Files

A model is a directory of JSON files, each validated against a meta-schema in `schemas/`. The files use the `.jsonc` extension — JSONC is just **JSON with comments**, so models can be documented inline:

* `concepts.jsonc` — entities, fields, relationships → [Backend.md](Backend.md#concepts)
* `security.jsonc` — roles, users, access rules → [Security.md](Security.md)
* `rules.jsonc` — business rules in FEEL → [Backend.md](Backend.md#business-rules-rulesjsonc)
* `backend/actions/*.js` — authenticated concept actions → [Backend.md](Backend.md#action-functions)
* `seed_data.jsonc` — initial sample records → [Backend.md](Backend.md#seed-data-seed_datajsonc)
* `deployed_data.jsonc` — model-owned rows synchronized on every deployment → [Backend.md](Backend.md#deployed-data-deployed_datajsonc)
* `workflow.jsonc` — state machines → [Workflow.md](Workflow.md)
* `presentation.jsonc` + `presentation/` — UI config and custom pages → [Frontend.md](Frontend.md)
* `presentation-custom-NN.jsonc` — role-scoped presentation overlays applied at runtime → [Frontend.md](Frontend.md#presentation-customization-overlays-presentation-custom-nnjsonc)
* `validations/` — CSV-defined valid field combinations → [Backend.md](Backend.md#validations-validationscsv)
* `system.jsonc` — runtime services such as SMTP and payments → [Deployment.md](Deployment.md#runtime-configuration-systemjsonc)
* `deployment.jsonc` — development and production deployment settings → [Deployment.md](Deployment.md#configuration-deploymentjsonc)
* `integrations.jsonc` and `backend/integrations/*.js` — external extraction, FEEL schema mapping and polling → [Integrations.md](Integrations.md)

Examples: `models/test-app` (e-commerce backoffice), `models/b2c-app` (storefront + admin), `models/cms-app` (public news site + admin with markdown + photos).

## Schema Reference

Every model file is validated against a self-documenting JSON Schema in [`schemas/`](../schemas). Each schema describes every property a model can use — its `description`, type, default, allowed values and constraints — so the schemas are the **canonical, exhaustive reference** for the model format, more detailed than the prose in these docs.

Concept, field and role names beginning with `_` are reserved for UniBizKit internals. Generated auxiliary tables and views are included in `concepts_extended.json`, and their effective ACL is included in `security_extended.json`.

Because each `.jsonc` file declares its `$schema`, editors with JSON Schema support surface these descriptions as inline autocompletion and validation while you write the model.

## The Extended IR

The generator validates each model file, injects defaults and enriches it with
internal `_`-prefixed metadata. This extended intermediate representation (IR)
is what every backend and frontend generator consumes, so framework-owned
concepts and permissions follow the same pipeline as user-defined ones.

The extended files (`concepts_extended.json`, `security_extended.json`,
`deployed_data_extended.json`, and others) are written beside the generated
application together with dynamically generated schemas. They are inspectable
build artifacts, not additional model inputs.

From that single IR, UniBizKit generates the complete application. The backend
output includes PostgreSQL schema and migrations, seed SQL, Supabase
configuration and Edge Functions under `<app>/backend/`; the frontend output
contains the React-Admin application under `<app>/frontend/`. Each application
gets its own Supabase instance in development and production. See
[Architecture.md](Architecture.md) for the runtime layout and
[Development.md](Development.md) for operating generated applications locally.

## Capabilities

What a model can express today, and where each is documented in detail:

* **Concepts** — business entities, each becoming a table and its CRUD UI → [Backend.md](Backend.md#concepts)
* **Field types** — `string`, `markdown`, `integer`, `decimal`, `enum`, `boolean`, `date`, `datetime`, `relation_to_one`, `relation_to_many`, `prefill`, and field `subtype`s such as `money` (currency rendering) → [Backend.md](Backend.md#field-types)
* **Relationships** — to-one and to-many (join tables), `part_of` ownership hierarchies vs. loose `related_to` references, and `prefill` fields that copy values from a related record. A to-one relation supports `on_delete: cascade`, `set_null`, or `snapshot_data`; `snapshot_data` stores the deleted record and lets the generated UI display it → [Backend.md](Backend.md#field-types)
* **Display labels** — `id_presentation` defines how each record is labelled and referenced across the UI, resolving related fields recursively (e.g. `Electronics / Keyboards`) → [Backend.md](Backend.md#concept-properties)
* **Calculated fields** — read-only values produced by strategies beyond plain columns: SQL expressions, `rollup(...)` aggregates over children, cross-record `copy(...)`/`copy_logged_on_insert(...)`, inline arithmetic, internal-variable binding (e.g. the logged-in user's email), and `by_rules` (delegated to a business rule) → [Backend.md](Backend.md#field-properties)
* **Constraints** — `required`, `unique`, `default`, `min`/`max`, `min_length`/`max_length`, type-specific `precision` (`decimal` digits or `datetime` granularity), `scale`, and concept-level `checks`, enforced in the database and mirrored as form validation → [Backend.md](Backend.md#field-properties)
* **Data-driven validations** — CSV files defining valid combinations of related field values (e.g. country → state → city) → [Backend.md](Backend.md#validations-validationscsv)
* **Business rules** — server-side logic in FEEL (`check`, `update` and `return` actions), fired synchronously (`when`) or asynchronously (`when_async`), compiled to edge functions that the frontend cannot bypass → [Backend.md](Backend.md#business-rules-rulesjsonc)
* **Workflows** — per-concept state machines with role-owned states, transitions and history → [Workflow.md](Workflow.md)
* **Documents** — versioned file/image attachments per record (by tag), stored in Supabase Storage buckets → [Backend.md](Backend.md#concept-properties)
* **Payments** — an optional payment edge function (provider proxy, with a dev simulator) charging a chosen amount field → [Deployment.md](Deployment.md#runtime-configuration-systemjsonc)
* **Security** — roles, users, and per-role/per-field access rules generated as PostgreSQL RLS policies, profile concepts, and SSO → [Security.md](Security.md)
* **Backend actions** — model-defined JavaScript functions exposed on list, edit and show views, including multi-row selection → [Backend.md](Backend.md#action-functions)
* **Presentation** — UI-wide settings, menus, list field/sort rules, and hand-written custom pages on top of the generated backend → [Frontend.md](Frontend.md)
* **Presentation designer** — visual in-app customization of menus, lists, forms, field labels and workflow-state visibility, with role-scoped overlays during development and per-user designs persisted in production → [Frontend.md](Frontend.md#design-mode)
* **Seed data** — initial and sample records, including embedded documents → [Backend.md](Backend.md#seed-data-seed_datajsonc)
* **Deployed data** — transactional upserts keyed by local `id_presentation` fields, with explicit ignore or delete behavior for rows removed from the authoritative model data → [Backend.md](Backend.md#deployed-data-deployed_datajsonc)
* **Size hints** — the field `size` (`s`/`m`/`l`) drives UI layout and the concept `data_size` hints expected volume → [Backend.md](Backend.md#field-properties)
* **External integrations** — protocol-specific JavaScript sources, FEEL mappings, `_external_id` upserts, polling, checkpoints and an operations UI → [Integrations.md](Integrations.md)
