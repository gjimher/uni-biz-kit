# UniBizKit - Developer Context

**UniBizKit** is a model-driven CLI tool that generates full-stack business applications from a declarative JSON schema. It currently targets **Supabase (PostgreSQL)** for the data layer and **React-Admin** for the presentation layer.

## Project Architecture

1.  **Input Model:** A directory containing:
    *   `concepts.json`: Defines business concepts, fields, and relationships (validated against `schemas/concepts_schema.json`).
    *   `presentation.json`: Configures UI-wide settings like currency, locales, and custom menus (validated against `schemas/presentation_schema.json`).
2.  **Core Logic (`src/unibizkit/`):**
    *   `cli.py`: Entry point handling arguments and commands.
    *   `schema_loader.py`: Validates and loads the input JSON schemas, injecting default values.
    *   `schema_processor.py`: Enriches the raw schema with internal metadata (`_`-prefixed fields).
    *   `supabase_generator.py`: Generates SQL DDL and sample data for PostgreSQL.
    *   `react_admin_generator.py`: Scaffolds a complete React-Admin frontend project.
3.  **Output:** A directory containing:
    *   `backend/`: SQL files.
    *   `frontend/`: React application.
    *   `concepts_extended.json`: The fully enriched IR (Intermediate Representation) used by generators.
    *   `concepts_extended_schema.json`: A dynamically generated JSON Schema used to validate the enriched IR.
    *   `presentation_extended.json` & `presentation_extended_schema.json`: Enriched presentation config and its schema.

## Project Structure

*   `src/unibizkit/`: Main package source code.
*   `schemas/`: 
    *   `concepts_schema.json`: The meta-schema for the user's business concepts.
    *   `presentation_schema.json`: The meta-schema for UI configuration.
    *   `concepts_extended_required_additions.json`: Defines the additional internal fields (like `_type`, `_be_sql_type`, `_fe_component`) that the `SchemaProcessor` adds during enrichment. This is merged with `concepts_schema.json` to create the `concepts_extended_schema.json` in the output folder.
*   `models/`: Business definitions used for testing and examples (e.g., `test-ecommerce-app/`).
*   `docs/`: Project documentation (`Development.md`, `USAGE.md`).
*   `tests/`: Integration and unit tests.
*   `test-ecommerce-app/`: Dedicated output directory for integration tests. **Do not delete this folder**, as it may contain cached dependencies (like `node_modules`).

## Development workflow

The project uses standard Python tooling.

Change generators, run pytest and check generated code in test-ecommcerce-app output directory.

To verify SQL generation:
```bash
pytest tests/test_ecommerce_backend.py
```

To verify Frontend generation:
```bash
pytest tests/test_ecommerce_frontend.py
```

To run all tests:
```bash
pytest
```

**Commit Messages:**
*   Write in English.
*   Keep them concise and focused on the *why* and *what*.

## Design Principles

*   **Simplicity over Architecture:** We prefer simple, maintainable code over complex architectural patterns.
*   **Naming Conventions:** React Admin components must follow `SCREAMING_SNAKE_CASE` conventions (e.g., `CREATE_ORDER_ITEM_FOR_ORDER`). This satisfies React and ESLint requirements for JSX components (which must be PascalCase or SCREAMING_SNAKE_CASE) while avoiding complex case conversion logic from the database's snake_case. When in doubt, we prioritize simplicity over aesthetic code style.
*   **Dictionary Access:**
    *   **Schema Fields:** Do not use `.get()` for fields that are marked as `required` or have a `default` value in `schemas/concepts_schema.json`. Trust the validation and enrichment process.
    *   **Extended Fields:** Fields starting with `_` (e.g., `_type`, `_be_sql_type`) are guaranteed to be populated by the `SchemaProcessor`. Always access them directly using brackets `[]` (e.g., `concept["_type"]`), **never** use `.get()`.