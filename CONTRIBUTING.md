# Contributing to UniBizKit

Thanks for your interest. UniBizKit is a personal, hobby project maintained by its author in
his own time and to his own taste. That shapes how contributions are handled — please read
this before opening a pull request.

## Bugs and questions

Found a bug or have a question? **Open an issue.** A clear report with steps to reproduce (and
the relevant model files, if any) is genuinely helpful and always welcome.

## New models and examples

Contributions that add or improve **models** (under `models/`) — new example applications,
richer sample data, fixes to existing ones — are welcome via pull request. See
[docs/Model.md](docs/Model.md) for how a model is structured.

Please keep a model self-contained and make sure it generates cleanly (`pytest`).

## Changes to the generator (`src/`)

The generator is the core of the project and I keep it deliberately small and consistent with
my own design choices. So, for anything touching `src/`:

- **Open an issue first** to discuss the idea before writing code.
- Unsolicited pull requests against the generator **may not be merged**, even if correct — not
  because the work isn't valued, but because reviewing and maintaining changes here costs time
  I may not have, and I'd rather keep the project focused than let it grow beyond what I can
  look after.

None of this is meant to discourage you. If an idea excites you and doesn't fit here, forking
is entirely welcome — that's what the Apache 2.0 license is for.

## Development

See [docs/Development.md](docs/Development.md) for the setup and workflow. Run the test suite
before submitting anything:

```bash
pytest
```

## Style

- Match the surrounding code and the project's [design principles](AGENTS-common.md#design-principles):
  simplicity over architecture.
- Commit messages in English, concise, focused on the *why*; prefix `refactor:` when behaviour
  doesn't change.
