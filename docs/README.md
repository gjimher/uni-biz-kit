# UniBizKit Documentation

## Contents

| Document | What it covers |
|----------|----------------|
| [USAGE.md](USAGE.md) | Install, quick start, running the generated applications |
| [Architecture.md](Architecture.md) | Layers, design principles, where to make changes |
| [Model.md](Model.md) | Model-driven development and the model files |
| [Backend.md](Backend.md) | Model format, generated database, edge functions |
| [Frontend.md](Frontend.md) | Generated UI, custom MDX/JSX pages, routing |
| [Security.md](Security.md) | Roles, ACL, RLS policies, profile concepts |
| [SingleSignOn.md](SingleSignOn.md) | Kerberos/Keycloak single sign-on |
| [Workflow.md](Workflow.md) | State machines on concepts |
| [Development.md](Development.md) | Dev environments, ports, `bin/dev-*` scripts |
| [Roadmap.md](Roadmap.md) | Planned work |

---

## Vision

Most companies end up building and maintaining many business applications that share the same concepts: customers, users, products, processes, permissions, and workflows.

UniBizKit's long-term vision is to become a **unified open-source stack for enterprise applications**, where:

* Business concepts are defined once
* Applications are generated from models, not handcrafted repeatedly
* Data, UI, security, and processes stay consistent
* Humans and AI agents can safely interact with business workflows

## Core Principles

* **Model-Driven Development**
  Business domains are defined using declarative models, not ad-hoc code. See [Model.md](Model.md).

* **Single Source of Truth**
  Domain models drive database schemas, APIs, and user interfaces.

* **Open and Portable**
  UniBizKit and every component it builds on are open source: self-hosted Supabase, PostgreSQL, React-Admin. Generated code is standard, readable, and editable. No runtime lock-in.

* **Enterprise-Ready**
  Designed for real-world business applications, not just demos.

* **Extensible by Design**
  Multiple data platforms, UI frameworks, and workflow engines can be supported over time.

## Current Architecture

See [Architecture.md](Architecture.md) for the full picture. In short:

* **Code generation engine** — implemented in Python, which is excellent for model processing and integrates well with AI tooling. Generators emit the code directly (no template engine).
* **Data layer** — [Supabase (PostgreSQL)](Backend.md): standard PostgreSQL with modern authentication and security, partially open-source and widely adopted. Other data platforms may be supported later.
* **Presentation layer** — [React-Admin](Frontend.md): mature and a strong fit for data-driven enterprise interfaces. Custom pages are written in MDX/JSX.

## Why UniBizKit?

UniBizKit is **not** a low-code platform and **not** a no-code tool.

Instead, it is:

* A toolkit for developers and AI agents
* A foundation for building enterprise stacks
* A way to industrialize application development without losing control

## Status

⚠️ **Early stage / experimental**

The project is under active design and development. APIs and models may change. See the [Roadmap](Roadmap.md).

Contributions, discussions, and feedback are welcome.
