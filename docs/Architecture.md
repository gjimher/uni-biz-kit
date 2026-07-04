# Architecture

UniBizKit follows a **KISS, layered, opinionated** architecture that makes practical use of existing open-source components (self-hosted Supabase, React-Admin) instead of building its own runtime.

The goal is to keep the implementation under control: independent pieces, decoupled from each other, so that an LLM can implement a complete application without introducing security or functional risks.

## Model-Driven Development

UniBizKit is a model-driven development (MDD) tool: the application is not written, it is **described** in a set of declarative model files, and a generator turns that description into a working stack. The model is the single source of truth — database schema, security policies, UI and business logic are all derived from it. See [Model.md](Model.md) for the model files and their format.

## Layers

| Layer | Contents | Docs |
|-------|----------|------|
| Model | JSON files: concepts, security, rules, workflow, presentation | [Model.md](Model.md), [Backend.md](Backend.md) |
| Backend | Supabase (PostgreSQL): schema, RLS, triggers, edge functions | [Backend.md](Backend.md), [Security.md](Security.md) |
| Frontend | React-Admin CRUD + custom MDX/JSX pages | [Frontend.md](Frontend.md) |
| Generator | Python package `src/unibizkit/` | [Development.md](Development.md) |

All security is enforced in the backend; the frontend is untrusted (see [Frontend.md](Frontend.md)).

## Change Levels

Changes can be made at several levels, each with a different risk:

1. **Model and business functions** — edit the JSON models and FEEL rules. Lowest risk: everything is validated and the generated backend enforces security. This is the level intended for functional users and AI agents.
2. **Presentation** — additionally write custom MDX/JSX pages for a tailored user interface. Moderate risk: UI bugs are possible, but the backend still enforces all security and business rules.
3. **Generator** — modify the Python code generator to fix or extend the capabilities of the models. Highest risk: affects every generated application; changes must be covered by the test suite.

## Idempotent Operations

The scripts that change the state of the stack — `start`, `stop`, `remove` — are **idempotent**: they can be run several times in a row without error. Each run simply makes sure the stack ends up in the requested state (starting what is stopped, applying pending config changes, doing nothing if there is nothing to do). This makes them safe to use in automation and by agents. The scripts are listed in [Development.md](Development.md#dev-scripts-appbindev-); each one documents its exact behavior in its `-h`.

## One Supabase Instance per Model

Both in development and in production, **each model gets its own Supabase instance**. This keeps models decoupled from each other, avoids monoliths, and simplifies operation (start, stop, reset, and deploy one application without touching the others). See [Development.md](Development.md) for how the dev instances are laid out.

## Integration Between Models

Models integrate with each other through business APIs: [edge functions](Backend.md#edge-functions) that call one another.

Sharing users between models is on the [roadmap](Roadmap.md) (one model using the user database of another). The current workaround is [Single Sign-On](SingleSignOn.md), already supported: all applications authenticate against the same identity provider.
