# Security in UniBizKit

UniBizKit provides a flexible, declarative security model to handle access control for your business applications. When authentication is required, you can define roles, users, and detailed security rules that are compiled into an Access Control List (`_acl`) for the system to enforce.

## The `_acl` Structure

The core of the security system resolves into an intermediate representation (`_acl`), which determines both **concept-level** and **field-level** access for each role.

### Structure Breakdown

For every concept, the `_acl` object contains two main sections:
1. `_main`: Concept-level access.
2. `_fields`: Field-specific access overrides.

```json
"_acl": {
  "ConceptName": {
    "_main": {
      "role_name": "read|write"
    },
    "_fields": {
      "field_name": {
        "role_name": "read|write"
      }
    }
  }
}
```

### Access Levels

- **`write`**: Allows the user to create, edit, and delete records (or specific fields).
- **`read`**: Restricts the user to only viewing the records (or specific fields).

### How Concept-Level and Field-Level Access Interact

The power of the `_acl` system is in how the `_main` rules and `_fields` rules combine to allow fine-grained permissions:

1. **Downgrading Access (Read-Only Fields)**
   If a role is granted `write` at the concept level (`_main`), they generally have full access to create, edit, and delete records of that concept.
   However, you can specify a `read` rule for a specific field in `_fields`. This **downgrades** their access, making that specific field read-only, even while the rest of the concept remains editable.

2. **Upgrading Access (Edit-Specific Fields)**
   Conversely, a role might only have `read` access at the concept level (`_main`), meaning they can only view the data and cannot create or delete records.
   By granting a `write` rule to specific fields in `_fields`, you allow the role to edit *only those specific fields* on existing records, while everything else remains read-only.

## How Rules are Resolved

When defining rules in `security.json` (`rules_level_1`, `rules_level_2`, `rules_level_3`), higher levels override lower levels.
- A rule applying to `field: "*"` sets the **concept-level (`_main`)** access.
- A rule applying to a specific field creates a **field-level override** in the `_fields` mapping.

This compiled `_acl` is then automatically translated into Row Level Security (RLS) policies and triggers in Supabase, and corresponding UI visibility constraints in React-Admin.
