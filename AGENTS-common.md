# UniBizKit - Developer Context

**UniBizKit** is a model-driven CLI that generates full-stack business applications (Supabase/PostgreSQL data layer, React-Admin presentation) from a declarative JSON model. Concepts and layers: [docs/Architecture.md](docs/Architecture.md); docs index: [docs/README.md](docs/README.md).

## Critical Instructions

*   **Python Command:** ALWAYS use `python`, NEVER `python3`.
*   **Plan Approval:** before making code, schema, test, documentation or generated-output changes, present a concrete plan and wait until the user accepts it. Do not edit files before the plan is accepted.
*   **Generate through pytest:** never run `uni-biz-kit` by hand during development. Change generators → `pytest` → inspect `test-app/` (dedicated output directory — do not delete it, it caches `node_modules`). `pytest tests/test_backend.py` verifies SQL and **recreates the database** (wipes `public`, cleans auth users); `pytest tests/test_frontend.py` verifies the frontend. Environments, ports and the second model (`UBK_DEV_MODEL`): [docs/Development.md](docs/Development.md).

## Layout

*   Input model (`models/<app>/`): `concepts.jsonc`, `presentation.jsonc`, `security.jsonc`, ... — each validated against its meta-schema in `schemas/`.
*   `src/unibizkit/`: `cli.py` → `schema_loader.py` (validate + defaults) → `schema_processor.py` (enriches with internal `_`-prefixed metadata) → `generators/{backend,frontend,prod,bin}`.
*   Generated output (`<app>/`): `backend/` SQL + Supabase config, `frontend/` React app, `bin/` dev/prod scripts, and `*_extended.json` (+ schemas): the enriched IR the generators consume.

## Design Principles

*   **Simplicity over Architecture:** we prefer simple, maintainable code over complex architectural patterns.
*   **Operational Commands:** idempotent whenever reasonably possible; detailed, current operational documentation through `-h` (effects, important ordering, destructive behavior, prerequisites, retry semantics).
*   **Source-of-Truth Documentation:** reference detail lives next to the source of truth (JSON Schema descriptions, command `-h`/docstrings, focused comments beside non-obvious behavior); higher-level docs explain workflows and link concepts together instead of duplicating material that can drift.
*   **Test Contracts, Not Implementation:** tests written only for implementation confidence are temporary — remove them before finishing. A permanent test pins something with an owner other than the code it checks (a behavior someone uses, a design decision, a non-obvious trap): ask *who breaks if this changes?* — if the answer is "only this test", do not write it. Prefer driving the real flow (E2E), then the existing compile/lint gates, and only then content asserts on generated artifacts (always with a comment stating the *why*). Never pin internal names, import paths or exported symbols — the project is in alpha and APIs change; a rename must not require editing tests.
*   **Naming Conventions:** React-Admin components use `SCREAMING_SNAKE_CASE` (e.g. `CREATE_ORDER_ITEM_FOR_ORDER`): JSX requires PascalCase or all-caps, and this avoids case conversions from the database's snake_case.
*   **Dictionary Access:** no `.get()` for schema fields that are `required` or have a `default`, nor for `_`-prefixed extended fields (`concept["_type"]`) — trust validation and enrichment.

## Commit Messages

*   English, concise, focused on the *why* and *what*: one short summary line, a blank line, then `-` detail bullets. Prefix with `refactor:` when the commit does not change functionality.
