# Architecture

UniBizKit is a model-driven CLI tool that generates full-stack business applications from a declarative JSON schema.

## Model-Driven Approach

The core idea is that the entire application structure, security, and presentation are defined in JSON models. These models are validated against schemas and then enriched into an Intermediate Representation (IR) that the generators use.

### Extension Mechanism

To avoid cluttering the input models with technical metadata, UniBizKit uses an extension mechanism:

1.  **Input Models:** `concepts.json`, `security.json`, `presentation.json`.
2.  **Validation Schemas:** Located in `schemas/`.
3.  **Required Additions:** `schemas/*_extended_required_additions.json` define the internal fields (prefixed with `_`) that the `SchemaProcessor` will add.
4.  **Enrichment:** The `SchemaProcessor` loads the input models, fills in defaults from the schemas, and calculates internal fields.
5.  **Output:** The enriched IR is saved in the output directory as `*_extended.json`, along with a dynamically generated `*_extended_schema.json` for validation and IDE support.

## Model Files

-   **`concepts.json`**: Defines the business entities (concepts), their fields, and relationships. It is the core of the application.
    -   Schema: `schemas/concepts_schema.json`.
-   **`security.json`**: Configures authentication requirements, user roles, and access control rules (RBAC). Rules can be defined at multiple levels with overrides.
    -   Schema: `schemas/security_schema.json`.
-   **`presentation.json`**: Defines UI-wide settings like locales, currency, and custom menus.
    -   Schema: `schemas/presentation_schema.json`.

All detail documentation for each field is located in their respective JSON schemas.
