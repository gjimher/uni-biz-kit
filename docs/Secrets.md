# Secrets

UniBizKit separates generated infrastructure credentials from custom Edge
Function secrets. Neither kind belongs in generated JavaScript, command-line
arguments or version control.

## Secret categories

### Supabase infrastructure credentials

PostgreSQL passwords, the JWT secret, and anon and service-role API keys are
generated for each Supabase instance. Development tooling writes the local
connection URL and keys to `<app>/backend/.env`. On the first production publish,
the deployment tooling creates them in `~/ubk/<app>/.env`; they survive version
switches and are deleted only by `prod-dc-remove.py`.

The anon key identifies the public API client and is intentionally included in
the generated frontend. It grants no privileges by itself: PostgreSQL row-level
security still authorizes every request. The service-role key bypasses those
policies and must remain exclusively in trusted backend and operational code.

These structural values are managed by UniBizKit. Do not edit or duplicate them
as custom secrets.

### Application and integration secrets

Credentials used by backend actions, payment providers or external integrations
are arbitrary uppercase keys matching `[A-Z][A-Z0-9_]*`. They do
not need to be declared in `integrations.jsonc` or another model file. Trusted
JavaScript reads them with `Deno.env.get("KEY")`; an integration source also
receives the complete environment as its `secrets` argument.

Keep non-secret endpoints and behavior in the model or source code. Store only
credentials and similarly sensitive values as secrets.

SMTP is not part of this secret mechanism. UniBizKit supports only
unauthenticated SMTP servers, configured by host, port and sender in
[`system.jsonc`](Deployment.md#runtime-configuration-systemjsonc).

## Development

Use the generated `dev-set-secret.py` command. With no input option it prompts
without echo; `--stdin` supports a password manager or another secret source:

```bash
python bin/dev-set-secret.py DYNAMICS_CLIENT_SECRET
secret-tool lookup service dynamics | python bin/dev-set-secret.py DYNAMICS_CLIENT_SECRET --stdin
python bin/dev-set-secret.py --list
python bin/dev-set-secret.py DYNAMICS_CLIENT_SECRET --delete
```

The command never accepts the value as an argument and `--list` prints names
only. Values are stored in the ignored `<app>/backend/.env.secrets` with mode
`0600`.

`dev-supabase-start.py` merges these values into
`backend/supabase/functions/.env` alongside the internal variables from
`.env.generated`. Generated internal variables take precedence, preventing a
custom secret from replacing the Supabase URL, keys or other framework-owned
configuration. Changing or deleting a secret reconciles the local stack only
when the effective Functions environment changes; database volumes are
preserved.

## Production

After the application has been published, use the generated command against
the server selected by `deployment.jsonc`:

```bash
python bin/prod-dc-set-secret.py DYNAMICS_CLIENT_SECRET
secret-tool lookup service dynamics | python bin/prod-dc-set-secret.py DYNAMICS_CLIENT_SECRET --stdin
python bin/prod-dc-set-secret.py --list
python bin/prod-dc-set-secret.py DYNAMICS_CLIENT_SECRET --delete
```

The same safe input and listing rules apply. Values live only in
`~/ubk/<app>/.env.secrets` with mode `0600`. Updating or deleting one recreates
only the Functions container, so Deno receives the new environment without
restarting PostgreSQL or the rest of the application. Structural variables
declared by the generated Compose service take precedence over this file.

Secret files are retained across ordinary deployments and version switches.
`prod-dc-remove.py` removes the complete application directory, including both
production secret files.
