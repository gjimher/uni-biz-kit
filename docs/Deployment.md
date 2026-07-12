# Production Deployment

Deploys a generated app as a **docker-compose stack** on a server reached over
SSH: a slim self-hosted Supabase (Postgres, Kong, GoTrue, PostgREST, Storage,
Edge Functions, Studio) plus an nginx serving the built SPA. Versions are
immutable and switched atomically; app data survives version switches.

## Requirements

* **Server**: reachable over SSH without password prompts, a user with
  passwordless sudo and access to the docker daemon, docker plus a compose
  implementation (`docker compose` plugin or classic `docker-compose`).
* **Workstation**: docker (to build and push the images) and the generated
  app's frontend able to build (`npm`).

## Configuration (`deployment.jsonc`)

In the model's `deployment.jsonc`:

| Field | Default | Meaning |
|-------|---------|---------|
| `prod_dcd_ssh_srv` | `ubk-prod` | SSH host of the server (alias from `~/.ssh/config` or `user@host`) |
| `prod_base_port` | `3000` | Base port; services are exposed at fixed offsets (below) |
| `prod_versioning` | required | `dev` for mutable resets or `git-tag` for versioned migrations |

Port layout (mirrors the dev layout in `generators/dev_ports.py`):

| Port | Service |
|------|---------|
| base + 0 | Frontend (nginx: SPA + `<base_uri>/api` proxy to Kong) |
| base + 40 | Supabase API (Kong) |
| base + 41 | Postgres |
| base + 43 | Supabase Studio (admin UI) |

`prod_versioning` has no default: every model must choose its deployment policy.

```jsonc
{
  "$schema": "../../schemas/deployment_schema.json",
  "base_uri": "/shop",
  "prod_dcd_ssh_srv": "ubk-prod",
  "prod_base_port": 3050,
  "prod_versioning": "git-tag"
}
```

The JSON Schema at `schemas/deployment_schema.json` is the complete reference,
including URL, SMTP and proxy options.

## Scripts

Generated in `<app>/bin/` (`dc` = docker-compose). All are idempotent and
document themselves in detail with `-h`:

```bash
python bin/prod-dc-check-infra.py  # once per server: checks ssh/sudo/docker/compose,
                                   # creates ~/ubk, launches the shared registry
python bin/prod-dc-publish.py      # prepare and upload; never changes DB/containers
python bin/prod-dc-up.py           # activate dev or the latest locally tagged release
python bin/prod-dc-up.py --version VERSION       # explicit rollback
python bin/prod-dc-remove.py       # remove everything: containers, DATA, images, secrets
```

Use `python bin/prod-dc-publish.py --dry-run` to validate and display the intended
work without changing Git, the database, Docker or the server.

## Development deployments

With `"prod_versioning": "dev"`, deployment deliberately has no Git
traceability requirement and accepts a dirty worktree. The two phases are:

1. `prod-dc-publish.py` builds and uploads mutable `dev` images without touching
   the running stack, database or storage.
2. `prod-dc-up.py` asks for confirmation (`--force` skips it).
3. Only after confirmation, `up` removes the PostgreSQL and Storage volumes.
4. `up` starts a clean stack and loads the complete schema, seed rows, seed documents
   and configured auth users.
5. `up` verifies the provisioner and frontend, then prunes dangling images.

All non-seed database rows, auth users and uploaded documents are lost. Proxy
models also use mutable `dev` images, but have no database volumes to reset.

## Git-tag releases

With `"prod_versioning": "git-tag"`, the version exists only in local tags named
`prod-<model>-vMAJOR.MINOR`. The first release is `v1.0`; later deployments bump
minor by default. `--major --allow-destructive` is required for a major release
that contains incompatible schema changes.

Publishing requires a clean, attached Git worktree. The first release of a
model (nothing deployed yet) packages the complete schema and skips the
compatibility check — there is no older artifact to protect. A later release
compares the deployed database to a shadow database built from the generated
complete schema, packages one Supabase migration relative to the preceding
release, validates it, uploads the artifact and manifest, and then creates the
annotated local tag. Publishing never applies SQL or changes active containers. `prod-dc-up.py` selects the newest local
tag, verifies it against the remote manifest, performs any required backup,
applies the migration, activates the artifact and runs health checks. UniBizKit
never reads or pushes Git remotes; publishing commits and tags is
the user's responsibility.

Minor releases reject table/column drops, renames, destructive type changes,
removed functions, mandatory columns without defaults, and constraints, unique
indexes or null/default changes that can break writes from the preceding
artifact. A major
release creates a complete custom-format dump in `~/ubk/<app>/backups/` and
validates it with `pg_restore --list` before applying destructive SQL.

The release manifest and built images contain the release version and exact Git
SHA. Supabase remains the migration authority through
`supabase_migrations.schema_migrations`; no UniBizKit migration table is added.

### Republishing a candidate

After `commit --amend`, `prod-dc-publish.py --republish` may replace the latest
local version and move its local tag after the artifact and manifest upload
succeed. Republication is accepted only when the normalized SQL
and migration hash are identical to what was already applied, so republication
never modifies the database. Changed schema requires a new version.

### Rollback

A minor rollback activates the prior compose artifact with
`prod-dc-up.py --version vMAJOR.MINOR` and leaves the additive database changes in
place. A major rollback is not automatic: stop the stack and restore its validated
pre-release dump. Rows written after that backup may be lost.

## How it works

Layout on the server:

```
~/ubk/<app>/
├── .env                          # secrets + PUBLIC_HOST (created on first publish)
├── docker-compose-<version>.yml  # one immutable file per published version
├── docker-compose.yml            # symlink to the active version
├── releases/<version>.sha256     # content hash guarding immutability
├── releases/<version>.json       # version, commit and migration metadata
└── releases/<version>.sql        # migration packaged for activation
```

* **Registry** — a `registry:2` container (`ubk-registry`, shared by all apps)
  bound to the server's loopback `:5000`. `prod-dc-publish.py` pushes through an
  SSH tunnel; the server pulls from `localhost:5000/<app>/...`, so no image
  ever needs a public registry.
* **Immutable versions** — publish computes a content hash of everything that
  defines the release (compose file, image build inputs, frontend build).
  `prod-dc-publish.py` creates the next version, or explicitly replaces the
  current candidate with `--republish` when its schema and migration are
  identical. Versions are never selected manually during publication.
* **Secrets** — Postgres password, JWT secret and the anon/service API keys are
  generated on the first publish and stored only in the server's
  `~/ubk/<app>/.env`. They survive version switches; `prod-dc-remove.py`
  deletes them.
* **Provisioning** — a one-shot `provision` container waits for Supabase. It
  loads the complete schema and seeds for a fresh database; versioned releases
  preserve existing data and apply only their pending Supabase migration.
* **Frontend build** — the production anon key and public URL are baked into
  the SPA at `vite build` time; the app talks to Supabase through the nginx
  `<base_uri>/api` proxy (same-origin, like the Vite dev proxy).

## Operations

```bash
# First deployment
python bin/prod-dc-check-infra.py
python bin/prod-dc-publish.py
python bin/prod-dc-up.py

# New minor / major release
python bin/prod-dc-publish.py
python bin/prod-dc-up.py
python bin/prod-dc-publish.py --major --allow-destructive
python bin/prod-dc-up.py

# Mutable dev activation without the destructive prompt
python bin/prod-dc-publish.py
python bin/prod-dc-up.py --force

# Roll back to a previous version (data is kept as-is)
python bin/prod-dc-up.py --version v1.2

# Tear down completely (asks for confirmation; -f to skip)
python bin/prod-dc-remove.py
```

To inspect the stack on the server: `cd ~/ubk/<app> && docker-compose ps`
(or `logs <service>`). If the server is behind NAT and only SSH is forwarded,
reach the app through a tunnel, e.g.
`ssh -L 3000:127.0.0.1:3000 <srv>` → `http://localhost:3000<base_uri>`.

## Proxy models (HTTPS landing + reverse proxy)

A **proxy** model is a second kind of model that puts a public HTTPS front in
front of the app stacks deployed on the same server. It contains **only** a
`deployment.jsonc` with a `proxy` section, an `index.md` (landing page) and an
`assets/` folder — no `concepts.jsonc` or other app sources (the two kinds are
mutually exclusive). The reference model is `models/ubk-app` (www.unibizkit.dev).

```jsonc
// models/ubk-app/deployment.jsonc
{
  "prod_versioning": "dev",
  "proxy": {
    "domain": "www.unibizkit.dev",   // HTTPS hostname (ACME TLS-ALPN-01)
    "acme_email": "you@example.com",  // optional Let's Encrypt account email
    "models": ["b2c-app"]             // app models to reverse-proxy, by name
  }
}
```

It generates a single **Caddy** container (`prod/docker/caddy/`) that:

* terminates HTTPS for `domain`, obtaining the certificate via **ACME
  TLS-ALPN-01 only** — the HTTP-01 challenge and the HTTP→HTTPS redirect vhost
  are disabled, so only port **443** needs to be reachable (fits a NAT that
  forwards only 443);
* serves the landing page at `/` (rendered from `index.md` to static HTML at
  build time, with the `assets/` images);
* reverse-proxies each referenced app at its own `base_uri` (e.g. `/b2c/* →
  127.0.0.1:3050`), read from that app's `deployment.jsonc` — the single source
  of truth for its `base_uri` and port (they must be unique across the list).
  The Caddy container runs with host networking, so it reaches the app ports on
  the host loopback interface.

The same `bin/prod-dc-*` scripts deploy it (no `dev-*` scripts are generated).
The ACME certificates live in the `caddy-data` volume and survive version
switches; `prod-dc-remove.py` deletes them, so the next deploy re-issues them
(mind Let's Encrypt rate limits). First `prod-dc-up.py` only passes its TLS
health check once the certificate is issued, which requires the public DNS A
record → NAT public IP with port 443 forwarded to this host.

## Production deployment test

`pytest --slow-prod tests/test_prod_deployment.py` explicitly enables a
destructive smoke test against `ubk-prod` on ports 6000–6046. It creates a
temporary `tmp/ubk-deploy-test-<id>` Git worktree and branch, deploys first in
`dev` and then in `git-tag`, and verifies the remote service and metadata. At the
start it removes previous `tmp/ubk-deploy-test-*` worktrees and branches. Cleanup
removes the remote deployment and local test tags, but retains the current
worktree and branch for inspection. It is independent from the normal `--slow`
option.
