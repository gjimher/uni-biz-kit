# Security in UniBizKit

UniBizKit provides a flexible, declarative security model to handle access control for your business applications. When authentication is required, you can define roles, users, and detailed security rules in `security.jsonc` (see [Backend.md](Backend.md#the-model-directory)) that are compiled into an Access Control List (`_acl`) for the system to enforce.

All enforcement happens in the backend — the [frontend](Frontend.md) is untrusted and only mirrors permissions for usability.

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

## Profile Concepts

A role can declare a `profile_concept` in `security.json`. When it does, every user who holds that role gets a linked record in the corresponding concept table. The link is maintained by five injected columns. Profile sync is based only on the identity values available in the token event: user UUID, email, and roles. It does not consult `auth.users` to check whether an old UUID still exists.

| Column | Purpose |
|--------|---------|
| `_user` | UUID currently linked to this profile. |
| `_user_email` | Email of the currently linked user. |
| `_user_prev` | UUID that was linked before this profile was deactivated or superseded. |
| `_user_email_prev` | Email that was linked before this profile was deactivated or superseded. Kept for audit. |
| `_user_pending_link` | Email of a pre-seeded profile waiting to be linked to a user for the first time. |

Profile records are created and linked automatically — the application never needs to manage this manually.

### States a profile record can be in

| `_user` | `_user_prev` | `_user_pending_link` | Meaning |
|---------|-------------|----------------------|---------|
| set | null | null | Active: linked to the most recent token identity for that email and role. |
| null | set | null | Inactive: the profile was unlinked because the same UUID lost the role, or because another UUID logged in with the same email. Reactivatable only by the UUID stored in `_user_prev`. |
| null | null | set | Pre-seeded: created by an admin before the user exists. Links on first login by email. |

### Profile sync at login

Every time Supabase issues or refreshes a JWT, the `custom_access_token_hook` runs. It derives `user_id`, `email`, and roles from the token event, then calls `sync_role_profiles(user_id, email, roles)`. Profile sync executes the following logic **for each role that has a `profile_concept`**:

**If the logged-in user does NOT hold the role:**

```
find the profile where _user = target_user_id:
    if found:
        profile._user_prev       = profile._user
        profile._user_email_prev = profile._user_email
        profile._user            = null
        profile._user_email      = null
```

The profile is deactivated in place. All business data is preserved. The previous user UUID is recorded in `_user_prev` so the deactivation is auditable and reversible.

**If the logged-in user DOES hold the role:**

```
if no profile with _user = target_user_id exists:

    deactivate active profiles with the same email but a different UUID:
        find profiles where _user_email = target_email
          and _user is not null
          and _user != target_user_id:
            profile._user_prev       = profile._user
            profile._user_email_prev = profile._user_email
            profile._user            = null
            profile._user_email      = null

    try to reactivate a deactivated profile:
        find profile where _user_prev = target_user_id:
            if found:
                profile._user            = target_user_id
                profile._user_email      = target_email
                profile._user_prev       = null
                profile._user_email_prev = null

    if still no profile linked:
        try to claim a pre-seeded profile:
            find profile where _user_pending_link = target_email and _user is null:
                if found:
                    profile._user              = target_user_id
                    profile._user_email        = target_email
                    profile._user_pending_link = null

    if still no profile linked:
        create a new profile record:
            _user  = target_user_id
            _user_email = target_email
            fields with default from_metadata(key, ...) = first non-empty
                key of the token's user_metadata (signUp options.data or
                SSO claims), null when every key is empty
```

### Mandatory profile fields

A profile field can declare `"required": "ask_after_login"` in `concepts.json`. The column stays nullable so the profile can be auto-created at login, but the UI treats it as mandatory: forms validate it as required, and the generated admin app shows a blocking "Complete your profile" dialog after login while any of these fields is still empty. A trigger rejects updates that clear a filled value back to null.

Combined with `"default": "from_metadata(...)"`, the value is usually collected at registration (the register page passes it as signUp metadata) or arrives in the SSO claims, and the dialog only appears when neither source provided it. See the property descriptions in [`schemas/concepts_schema.json`](../schemas/concepts_schema.json) for the exact rules.

### Same-Email, New-UUID Login

In federated deployments, the application may not be able to ask the identity store whether an old UUID still exists. The sync logic therefore treats email as the continuity key for displacement, while still treating UUID as the continuity key for reactivation.

If a token arrives with the same email but a different UUID from the currently linked profile, the hook sees that there is no profile where `_user = new_uuid`. It then:

1. Deactivates active profiles where `_user_email = email` and `_user` is a different UUID.
2. Tries to reactivate a profile where `_user_prev = new_uuid`.
3. Tries to claim a pre-seeded profile where `_user_pending_link = email` and `_user IS NULL`.
4. Creates a fresh profile if neither exists.

This cleanup does **not** transfer the old profile to the new UUID. The old profile is moved to the inactive state with `_user_prev = old_uuid`, and the same-email, new-UUID user gets a new profile unless an admin prepared a `_user_pending_link` row for that email.

### Reactivation is UUID-based, not email-based

A deactivated profile can only be reactivated by the exact same user UUID that was previously linked (`_user_prev = target_user_id`). If a different UUID appears with the same email address, it will **not** inherit that deactivated profile. It will either claim a pre-seeded record via `_user_pending_link` or get a fresh one. The deactivated profile remains frozen until its original UUID reappears, or until an admin intervenes directly.

This means federation scenarios where the same person acquires a new UUID (e.g. migrated to a different identity provider) require a manual admin step to re-link the profile.

### Timing

Role-based deactivation happens at JWT issuance — the user's next login or token refresh. A user whose role is revoked retains their active JWT for up to the token's remaining lifetime (Supabase default: **1 hour**). Once the JWT expires and the client refreshes, the hook fires for the same UUID, the profile is deactivated, and the new JWT reflects the updated role list. RLS policies then immediately deny access to the previously accessible records.

User deletion in the identity system has different timing: there is no hook at the moment the UUID disappears, so the old profile remains active locally until another token event is seen. A later login with the same email and a new UUID deactivates the old local profile, then creates or claims a separate profile as described above.

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

The full SSO login flow and its dev environment are described in [SingleSignOn.md](SingleSignOn.md). SSO roles flow through two separate mechanisms:

#### 1. At JWT issuance — `custom_access_token_hook`

Every time Supabase generates a JWT (login or token refresh), the `custom_access_token_hook` function runs. It:

1. Reads the role claim from the token event claims. The hook does not need to look up the user in `auth.users` or `auth.identities`.
2. Extracts the role claim from these paths in order:
   - `claims -> 'roles'` (standard Keycloak)
   - `claims -> 'user_metadata' -> 'roles'`
   - `claims -> 'custom_claims' -> 'roles'`
   - `claims -> 'realm_access' -> 'roles'` (Keycloak realm access)
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
| SSO provider sends different roles | Yes | `custom_access_token_hook` picks up the new token claims on the next token refresh; `on_auth_user_roles_sync` trigger can also persist roles when Supabase writes matching raw metadata |
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
- **In the JWT (`app_metadata.roles`):** Valid for the lifetime of the access token (Supabase default: **1 hour**). After expiry, the client must refresh the token, at which point `custom_access_token_hook` re-reads the latest role claims from the token event and re-embeds them in the new JWT.

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
