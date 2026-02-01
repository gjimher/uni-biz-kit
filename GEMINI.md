# UniBizKit - Developer Context

**UniBizKit** is a model-driven CLI tool that generates full-stack business applications from a declarative JSON schema. It currently targets **Supabase (PostgreSQL)** for the data layer and **React-Admin** for the presentation layer.

## Project Architecture

1.  **Input Model:** A JSON file defining business concepts, fields, and relationships (validated against `schemas/business_schema.json`).
2.  **Core Logic (`src/unibizkit/`):**
    *   `cli.py`: Entry point handling arguments and commands.
    *   `schema_loader.py`: Validates and loads the input JSON schema.
    *   `supabase_generator.py`: Generates SQL DDL and sample data for PostgreSQL.
    *   `react_admin_generator.py`: Scaffolds a complete React-Admin frontend project.
3.  **Output:** A directory containing `backend/` (SQL files) and `frontend/` (React application).

## Project Structure

*   `src/unibizkit/`: Main package source code.
*   `schemas/`: Contains the meta-schema (`business_schema.json`) defining the contract for input models.
*   `examples/`: Sample business definitions (e.g., `ecommerce_schema.json`).
*   `tests/`: Integration and unit tests.
*   `test-ecommerce-app/`: Dedicated output directory for integration tests. **Do not delete this folder**, as it may contain cached dependencies (like `node_modules`).
*   `ecommerce-app/`: A reference implementation ("golden master") used for comparison and guiding generator improvements.

## Development Setup

The project uses standard Python tooling.

**Installation:**
```bash
pip install -r requirements-dev.txt
pip install -e .
```

## CLI Usage

The primary entry point is `unibizkit`.

**Validate a Schema:**
```bash
unibizkit validate examples/ecommerce_schema.json
```

**Generate an Application:**
```bash
unibizkit generate examples/ecommerce_schema.json --output-dir my-output-dir
```

## Testing & Verification

**Important Rules:**
*   **Preserve `test-ecommerce-app`:** The tests automatically clean relevant files inside this directory but preserve heavy artifacts like `node_modules`. Never delete the directory itself.
*   **Use Tests for Verification:** Instead of manually running `unibizkit` and checking files, rely on the integration tests.
*   **Timeouts:** Tests may run for longer than 60 seconds.

**Running Tests:**

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

## Contribution Workflow

1.  **Analyze Reference:** Check `ecommerce-app/frontend` for desired code patterns.
2.  **Modify Generator:** Update `src/unibizkit/` to match those patterns.
3.  **Verify:** Run `pytest tests/test_ecommerce_frontend.py` to generate code into `test-ecommerce-app`.
4.  **Compare:** Compare `test-ecommerce-app/frontend` with `ecommerce-app/frontend` to ensure correctness.

**Commit Messages:**
*   Write in English.
*   Keep them concise and focused on the *why* and *what*.

## Design Principles

*   **Simplicity over Architecture:** We prefer simple, maintainable code over complex architectural patterns.
*   **Naming Conventions:** React Admin components must follow `SCREAMING_SNAKE_CASE` conventions (e.g., `CREATE_ORDER_ITEM_FOR_ORDER`). This satisfies React and ESLint requirements for JSX components (which must be PascalCase or SCREAMING_SNAKE_CASE) while avoiding complex case conversion logic from the database's snake_case. When in doubt, we prioritize simplicity over aesthetic code style.