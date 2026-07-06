# UniBizKit

**UniBizKit** generates complete, secure business applications (e-commerce, CRM, ERP, intranets) from a declarative model. Define the model once; get a working full-stack application.

Website: [www.unibizkit.dev](https://www.unibizkit.dev) — with live demos you can sign into (a B2C shop and an intranet).

## What it is

A model-driven development (MDD) tool. An application is a directory of JSON files that define:

* **Concepts** — entities, fields, relationships
* **Security** — roles, users, access rules
* **Validations** — data-driven field validations
* **Business rules** — server-side functions written in a business language (FEEL)
* **Workflow** — state machines with role ownership

From that model, a Python generator produces:

* A **Supabase (PostgreSQL)** backend: schema, Row Level Security, triggers and edge functions.
* A **React-Admin** frontend: full CRUD editing for every concept.
* Optionally, a custom end-user interface defined as Markdown (MDX) or JSX pages on top of the generated stack.

Everything is open source: UniBizKit itself (Apache 2.0) and the whole stack it builds on — self-hosted Supabase, PostgreSQL and React-Admin. No SaaS dependencies, no runtime lock-in.

## Why

It is easier to obtain a quality application — without functional or security problems — by having an agent write a model than by having it write code. The goal is that a functional user, helped by an AI agent, builds an application by writing its model. Correctness and security are enforced by the generated backend, not left to hand-written code.

## Examples

* [`models/test-app`](models/test-app) — e-commerce backoffice, used by the test suite.
* [`models/b2c-app`](models/b2c-app) — B2C storefront: custom MDX/JSX front for customers plus the generated admin UI.
* [`models/cms-app`](models/cms-app) — content manager: a public news site plus an admin where employees publish articles with a markdown editor and photos.

## Documentation

* [docs/USAGE.md](docs/USAGE.md) — install and quick start.
* [docs/README.md](docs/README.md) — documentation index and project vision.

## Status

Early stage / experimental. APIs and models may change.

## License

Apache License 2.0
