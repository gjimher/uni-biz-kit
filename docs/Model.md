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

Examples: `models/test-app` (e-commerce backoffice), `models/b2c-app` (storefront + admin).

## The Extended IR

The generator validates each file, injects defaults, and enriches the result with internal `_`-prefixed metadata. The enriched intermediate representation is written next to the generated code (`concepts_extended.json`, `security_extended.json`, …) together with a dynamically generated schema for each, so it can be inspected and validated.
