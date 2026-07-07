# The Model

UniBizKit is a **model-driven development** (MDD) tool: an application is not written, it is *described*. The model is the single source of truth — database schema, security policies, business logic and UI are all generated from it, so they can never drift apart.

This is what makes the approach safe for AI agents: an agent (or a functional user) produces a declarative model, and the generator turns it into a stack whose correctness and security do not depend on the quality of hand-written code. See [Architecture.md](Architecture.md#change-levels) for the levels at which changes can be made.

## Model Files

A model is a directory of JSON files, each validated against a meta-schema in `schemas/`. The files use the `.jsonc` extension — JSONC is just **JSON with comments**, so models can be documented inline:

* `concepts.jsonc` — entities, fields, relationships → [Backend.md](Backend.md#concepts)
* `security.jsonc` — roles, users, access rules → [Security.md](Security.md)
* `rules.jsonc` — business rules in FEEL → [Backend.md](Backend.md#business-rules-rulesjsonc)
* `workflow.jsonc` — state machines → [Workflow.md](Workflow.md)
* `presentation.jsonc` + `presentation/` — UI config and custom pages → [Frontend.md](Frontend.md)
* `seed_data.jsonc`, `system.jsonc`, `deployment.jsonc`, `validations/` → [Backend.md](Backend.md#the-model-directory)

Examples: `models/test-app` (e-commerce backoffice), `models/b2c-app` (storefront + admin), `models/cms-app` (public news site + admin with markdown + photos).

## Schema Reference

Every model file is validated against a self-documenting JSON Schema in [`schemas/`](../schemas). Each schema describes every property a model can use — its `description`, type, default, allowed values and constraints — so the schemas are the **canonical, exhaustive reference** for the model format, more detailed than the prose in these docs.

Because each `.jsonc` file declares its `$schema`, editors with JSON Schema support surface these descriptions as inline autocompletion and validation while you write the model.

## The Extended IR

The generator validates each file, injects defaults, and enriches the result with internal `_`-prefixed metadata. The enriched intermediate representation is written next to the generated code (`concepts_extended.json`, `security_extended.json`, …) together with a dynamically generated schema for each, so it can be inspected and validated.

## Capabilities

What a model can express today, and where each is documented in detail:

* **Concepts** — business entities, each becoming a table and its CRUD UI → [Backend.md](Backend.md#concepts)
* **Field types** — `string`, `markdown`, `integer`, `decimal`, `enum`, `boolean`, `date`, `datetime`, `relation_to_one`, `relation_to_many`, `prefill` → [Backend.md](Backend.md#field-types)
* **Relationships** — to-one and to-many (join tables), `part_of` ownership hierarchies, and `prefill` fields that copy values from a related record → [Backend.md](Backend.md#field-types)
* **Calculated fields** — read-only values computed by PostgreSQL: SQL expressions or `rollup(...)` aggregates over child records → [Backend.md](Backend.md#field-properties)
* **Constraints** — `required`, `unique`, `default`, `min`/`max`, `min_length`/`max_length`, `precision`/`scale`, and concept-level `checks`, enforced in the database and mirrored as form validation → [Backend.md](Backend.md#field-properties)
* **Data-driven validations** — CSV files defining valid combinations of related field values (e.g. country → state → city) → [Backend.md](Backend.md#validations-validationscsv)
* **Business rules** — server-side logic in FEEL (`check` and `update` actions), compiled to edge functions that the frontend cannot bypass → [Backend.md](Backend.md#business-rules-rulesjsonc)
* **Workflows** — per-concept state machines with role-owned states, transitions and history → [Workflow.md](Workflow.md)
* **Documents** — file/image attachments per record, stored in Supabase Storage buckets → [Backend.md](Backend.md#concept-properties)
* **Security** — roles, users, and row-level access rules generated as PostgreSQL RLS policies, plus SSO → [Security.md](Security.md)
* **Presentation** — UI-wide settings, menus, and hand-written custom pages on top of the generated backend → [Frontend.md](Frontend.md)
* **Seed data** — initial and sample records, including embedded documents → [Backend.md](Backend.md#seed-data-seed_datajsonc)
* **Size hints** — the field `size` (`s`/`m`/`l`) drives UI layout and the concept `data_size` hints expected volume → [Backend.md](Backend.md#field-properties)