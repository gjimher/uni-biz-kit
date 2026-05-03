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
      "role_name": "read|write|owner_write"
    },
    "_fields": {
      "field_name": {
        "role_name": "read|write|owner_write"
      }
    }
  }
}
```

### Access Levels

- **`write`**: Allows the user to create, edit, and delete records (or specific fields).
- **`owner_write`**: Grants write access strictly to the owner of the record. When a concept uses `owner_write`, UniBizKit automatically injects a `security_owner_id` column (defaulting to the authenticated user ID) and generates corresponding Row Level Security (RLS) policies to ensure users can only modify their own data. Note: `owner_write` inherently grants read access as well.
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

---

## The `_anon` Built-in Role

UniBizKit includes a special built-in role named `_anon` that represents **unauthenticated users** — anyone accessing the application without a login session. It maps directly to the `anon` PostgreSQL role that Supabase exposes for requests made without a JWT.

### How it works

When a request reaches Supabase without a valid JWT (or with only the public anon API key), Supabase sets the PostgreSQL session role to `anon`. Row Level Security then evaluates policies against that role. By adding `_anon` rules in your security configuration, you can opt specific concepts into public read access.

### Usage

Use `_anon` as the `role` in any security rule, with `access: "read"`:

```json
{
  "rules_level_2": [
    { "concept": "product", "role": "_anon", "access": "read", "field": "*" }
  ]
}
```

This generates the following RLS policy:

```sql
CREATE POLICY "anon_read_product" ON "product"
FOR SELECT
TO anon
USING (true);
```

### Constraints

- **`_anon` is read-only.** Using `write` or `owner_write` with `_anon` raises a generation error. There is no stable user identity for anonymous sessions, so writes would be unattributable and untraceable.
- **`_anon` does not need to be declared in the `roles` list.** It is a built-in — declaring it there has no effect and is not required.
- **Rule propagation applies normally.** A `_anon read` rule on a parent concept (e.g. `product`) propagates to its child concepts (e.g. `order_item`) following the same logic as other roles. Override with a higher-priority rule if needed.

### Frontend behavior

The React frontend uses a single shared Supabase client for all pages (both public and authenticated). The client automatically includes the JWT when a session is active, and omits it when there is none. Supabase selects the correct set of RLS policies (`anon` vs `authenticated`) server-side, so the dataProvider requires no special configuration for public pages.

Public pages (those not matching the `authenticated_pages` patterns in `presentation.json`) are rendered without the React Admin `<Authenticated>` wrapper and are therefore accessible without login.

---

## Backend Implementation: Role Lifecycle

This section covers how roles are stored, assigned, and enforced at the database level. The frontend has **no security enforcement**; all access control is implemented exclusively in the backend.

### Where Roles Are Stored

Roles are **not stored in custom tables**. They live in two JSONB columns of Supabase's built-in `auth.users` table:

| Column | Purpose |
|--------|---------|
| `raw_app_meta_data.roles` | Canonical role array used by RLS policies (e.g. `["admin", "user"]`) |
| `raw_user_meta_data` | Temporary landing zone for SSO identity claims before they are synced |

The RLS policies always read from `auth.jwt() -> 'app_metadata' -> 'roles'`, which at runtime reflects `raw_app_meta_data.roles` as embedded in the JWT.

### Role Assignment for Email/Password Users

When a new user registers (or is seeded by the dev script):

1. The Supabase Admin API creates the user with `app_metadata: { roles: [...] }`.
2. If no roles are provided, the `on_auth_user_roles_sync` trigger fires on `INSERT` and assigns the default role defined in `security.json` → `registration.role`.
3. The assigned role is persisted in `raw_app_meta_data.roles` and is included in every JWT issued for that user.

### Role Assignment for SSO Users (Keycloak / OIDC)

SSO roles flow through two separate mechanisms:

#### 1. At JWT issuance — `custom_access_token_hook`

Every time Supabase generates a JWT (login or token refresh), the `custom_access_token_hook` function runs. It:

1. Reads the SSO identity row for the user from `auth.identities` (provider ≠ `'email'`).
2. Extracts the role claim from the identity data, checking these paths in order:
   - `identity_data -> 'roles'` (standard Keycloak)
   - `identity_data -> 'custom_claims' -> 'roles'`
   - `identity_data -> 'realm_access' -> 'roles'` (Keycloak realm access)
3. Filters the extracted roles against the whitelist defined in `security.json` → `roles[*].name`. Invalid roles are silently dropped.
4. Injects the filtered roles into the JWT under `app_metadata.roles`.
5. If the SSO token contained roles but none passed the whitelist, the user falls back to `security.json` → `sso.default_role`.

This means the **JWT always reflects the SSO provider's current roles**, re-evaluated at every token refresh.

#### 2. At user creation/update — `on_auth_user_roles_sync` trigger

When Supabase first creates an SSO user (or updates their `raw_user_meta_data`), the trigger also syncs the role into `raw_app_meta_data.roles` via the same claim-path logic and whitelist filtering. This ensures the persisted value in `auth.users` stays consistent with the JWT.

### Can Roles Be Changed?

| Scenario | Allowed? | Mechanism |
|----------|---------|-----------|
| Admin changes a user's role | Yes | Direct update to `auth.users.raw_app_meta_data` via the Supabase Admin API (service role key required) |
| SSO provider sends different roles | Yes | `custom_access_token_hook` picks up the new claims on the next token refresh; `on_auth_user_roles_sync` trigger updates `raw_app_meta_data` |
| User changes their own role | **No** | `auth.users` is not exposed through the PostgREST API at all; it is an internal Supabase table |
| Web app changes any user's role | **No** | The web application only holds the **anon key**, which never grants access to `auth.users` or the Admin API |
| Role not on the whitelist | **No** | Filtered out silently by both the trigger and the JWT hook |

#### Why the web app cannot change roles

The web application authenticates requests with Supabase's **anon key** (a public, low-privilege JWT). This key:

- Has access only to the tables exposed via PostgREST under the `public` schema, subject to RLS.
- Has **no access to `auth.users`**, which is an internal Supabase schema not reachable through PostgREST.
- Has **no access to the Admin API** (`/auth/v1/admin/...`), which requires the **service role key** — a secret that must never leave the server and is not present in the web app.

The only path to changing a role from the application layer would be a vulnerability in Supabase itself (e.g. a privilege-escalation bug in PostgREST or the auth service). Short of that, role changes require either the service role key or direct database access.

### How Long the Role Is Maintained

Roles have two independent lifetimes:

- **In the database (`raw_app_meta_data.roles`):** Persists indefinitely until explicitly changed via the Admin API or through an SSO sync.
- **In the JWT (`app_metadata.roles`):** Valid for the lifetime of the access token (Supabase default: **1 hour**). After expiry, the client must refresh the token, at which point `custom_access_token_hook` re-reads the latest roles from `auth.identities` and re-embeds them in the new JWT.

For SSO users this means: if an admin revokes a role in Keycloak, the user retains their current roles in the active JWT for up to 1 hour. The change takes effect on the next token refresh.

### How RLS Policies Enforce Roles at Runtime

Every generated table has RLS enabled. Policies use the `?` JSONB containment operator to check the JWT:

```sql
-- Read access for role "user"
USING (auth.jwt() -> 'app_metadata' -> 'roles' ? 'user')

-- Owner-scoped write (user can only modify their own rows)
WITH CHECK (
  auth.jwt() -> 'app_metadata' -> 'roles' ? 'user'
  AND "security_owner_id" = auth.uid()::text
)
```

Field-level restrictions are enforced by `BEFORE INSERT OR UPDATE` triggers that raise `insufficient_privilege` if a caller without the required role attempts to write a protected field.

### Internal Columns

Columns whose name starts with `_` are reserved for UniBizKit internals. A model cannot define fields with this prefix.

All generated tables include two standard triggers for internal columns:

- `00_protect_internal_columns_trigger` rejects `INSERT` values for `_...` columns and rejects any `UPDATE` that changes them.
- `01_set_system_timestamps_trigger` assigns `_created_at` and `_updated_at` after the protection trigger has validated the user-supplied row.

This means the UI cannot create or modify internal columns. If a request sends `_created_at`, `_updated_at`, or any other `_...` column, the database rejects it.

### Bypass for Database Seeding

Triggers and security functions check whether a JWT is present in the current request context:

```sql
IF current_setting('request.jwt.claims', true) IS NULL OR
   current_setting('request.jwt.claims', true) = '' THEN
    -- No JWT: direct DB connection (seed scripts, migrations). Bypass enforcement.
    IF (TG_OP = 'DELETE') THEN RETURN OLD; ELSE RETURN NEW; END IF;
END IF;
```

This allows seed scripts run via the service role (which bypass the PostgREST JWT layer) to populate data without triggering permission errors.

This bypass applies to permission and ACL enforcement triggers, including `00_protect_internal_columns_trigger`. 
Direct database seed and migration scripts may therefore populate `_...` columns when they run without a PostgREST user JWT. 
Requests made through the application with a user JWT still cannot create or modify internal columns.

`01_set_system_timestamps_trigger` always runs; system timestamps remain database-controlled even during seeding.
