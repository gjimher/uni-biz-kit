# UniBizKit

**UniBizKit** is an open-source, model-driven toolkit for building unified business applications such as CRM, ERP, intranets, and other enterprise data-driven systems.

The project aims to provide a **single, declarative source of truth** to define business domains and automatically generate consistent data models, user interfaces, and application scaffolding, while remaining fully extensible and vendor-neutral.

## Vision

Most companies end up building and maintaining many business applications that share the same concepts: customers, users, products, processes, permissions, and workflows.

UniBizKit’s long-term vision is to become a **unified open-source stack for enterprise applications**, where:

* Business concepts are defined once
* Applications are generated from models, not handcrafted repeatedly
* Data, UI, security, and processes stay consistent
* Humans and AI agents can safely interact with business workflows

## Core Principles

* **Model-Driven Development**
  Business domains are defined using declarative models, not ad-hoc code.

* **Single Source of Truth**
  Domain models drive database schemas, APIs, and user interfaces.

* **Open and Portable**
  Generated code is standard, readable, and editable. No runtime lock-in.

* **Enterprise-Ready**
  Designed for real-world business applications, not just demos.

* **Extensible by Design**
  Multiple data platforms, UI frameworks, and workflow engines are supported over time.

## Current Architecture (Initial Phase)

UniBizKit is currently focused on establishing a strong and pragmatic foundation.

### 1. Domain Modeling

* Business concepts are defined using a custom JSON-based schema.
* Models describe:

  * Entities and fields
  * Data types and constraints
  * Relationships
  * Basic presentation metadata

These models act as the **core contract** of the system.

---

### 2. Code Generation Engine

* Implemented in **Python**
* Python was chosen because:

  * It is excellent for model processing and automation
  * It integrates well with AI tooling
  * It is widely adopted and easy to extend
* Code is generated using templates (e.g. Jinja2)

The generator is designed to be **plugin-based**, allowing new targets to be added over time.

---

### 3. Data Layer (Current Default)

* **Supabase (PostgreSQL)** is used as the initial data platform.
* UniBizKit generates:

  * Database tables
  * Relationships and constraints
  * Supporting metadata

Supabase was chosen because it:

* Is built on standard PostgreSQL
* Supports modern authentication and security patterns
* Is partially open-source and widely adopted

> Future versions will support alternative data platforms (e.g. plain PostgreSQL, Hasura-based stacks, or other backends).

---

### 4. Presentation Layer (Current Default)

* **React-Admin** is used as the initial admin UI framework.
* From the domain model, UniBizKit generates:

  * List views
  * Create/Edit forms
  * Filters and search
  * Relationship views

React-Admin was selected for its maturity and strong fit for data-driven enterprise interfaces.

> Other frontend approaches (e.g. Refine or custom UI stacks) are planned as future extensions.

---

## Roadmap (High-Level)

UniBizKit is intentionally developed in phases.

### Short Term

* Stabilize the domain schema
* Improve code generation pipelines
* Add validation and tooling around models

### Mid Term

* Support multiple data platforms
* Support multiple UI frameworks
* Introduce stronger security and authorization modeling

### Long Term

* Integrate a **workflow engine**
* Model business processes explicitly
* Support human-in-the-loop workflows
* Enable AI agents as first-class workflow participants
* Provide visual workflow representations

---

## Why UniBizKit?

UniBizKit is **not** a low-code platform and **not** a no-code tool.

Instead, it is:

* A toolkit for developers
* A foundation for building enterprise stacks
* A way to industrialize application development without losing control

---

## Status

⚠️ **Early stage / experimental**

The project is under active design and development. APIs and models may change.

Contributions, discussions, and feedback are welcome.

---

## License

Apache License 2.0

---

