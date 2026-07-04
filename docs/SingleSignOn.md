# Single Sign-On

UniBizKit applications can authenticate users against a corporate identity provider instead of (or alongside) email/password. The supported setup is **Kerberos → Keycloak → OIDC → Supabase**: the user logs into their desktop once and enters the application without typing a password.

SSO is also the current mechanism for sharing users **across applications**: every model authenticates against the same identity provider (a proper shared user database is on the [roadmap](Roadmap.md), see [Architecture.md](Architecture.md#integration-between-models)).

## Configuration

Enabled in `security.jsonc`:

```jsonc
"sso": {
  "enabled": true,
  "domain": "dev.local",     // Kerberos realm / email domain of SSO users
  "role_claim": "roles",     // JWT claim carrying the roles from the provider
  "default_role": "user"     // fallback when no whitelisted role is found
}
```

## Login Flow

1. The user's desktop session holds a **Kerberos ticket** (corporate domain login).
2. The login page offers an SSO button that calls `supabase.auth.signInWithOAuth({ provider: 'keycloak' })`.
3. The browser is redirected to **Keycloak**, which authenticates it transparently via SPNEGO/Kerberos — no password prompt.
4. Keycloak returns **OIDC** tokens to Supabase Auth, which creates/updates the user and issues the application JWT.
5. At JWT issuance, the `custom_access_token_hook` extracts the roles from the provider's claims, filters them against the roles declared in `security.jsonc`, and injects them into `app_metadata.roles`. Invalid roles are dropped; if none survive, `sso.default_role` applies.

Role management therefore lives in the identity provider: roles are re-evaluated on **every token refresh**, so a role revoked in Keycloak takes effect within the token lifetime (1 hour by default). The details of role extraction, whitelisting, persistence and profile syncing are in [Security.md](Security.md#role-assignment-for-sso-users-keycloak--oidc).

## Dev Environment

When SSO is enabled, the generated app includes `dev-sso-*` scripts (see [Development.md](Development.md#dev-scripts-appbindev-)) that bring up a self-contained environment with Docker Compose:

* **MIT Kerberos KDC** — the "corporate domain", with principals for the model's users.
* **Keycloak** — configured automatically: realm, SPNEGO, the OIDC client for Supabase, and the users/roles from the generated `security_extended.json`.

```bash
python test-app/bin/dev-sso-start.py    # start and auto-configure KDC + Keycloak
python test-app/bin/dev-sso-chrome.py   # get a Kerberos ticket and launch Chrome
```

`dev-sso-chrome.py` obtains a ticket for a test user and launches Chrome configured for SPNEGO, reproducing the corporate desktop experience: open the app, click the SSO button, and enter without a password. Ports and container naming follow the per-environment layout in [Development.md](Development.md#port-table).
