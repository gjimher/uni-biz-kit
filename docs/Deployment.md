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

## Configuration

In the model's `deployment.jsonc`:

| Field | Default | Meaning |
|-------|---------|---------|
| `prod_dcd_ssh_srv` | `ubk-prod` | SSH host of the server (alias from `~/.ssh/config` or `user@host`) |
| `prod_base_port` | `3000` | Base port; services are exposed at fixed offsets (below) |
| `prod_version` | `v1` | Version name published/activated by default |

Port layout (mirrors the dev layout in `generators/dev_ports.py`):

| Port | Service |
|------|---------|
| base + 0 | Frontend (nginx: SPA + `<base_uri>/api` proxy to Kong) |
| base + 40 | Supabase API (Kong) |
| base + 41 | Postgres |
| base + 43 | Supabase Studio (admin UI) |

## Scripts

Generated in `<app>/bin/` (`dc` = docker-compose). All are idempotent and
document themselves in detail with `-h`:

```bash
python bin/prod-dc-check-infra.py  # once per server: checks ssh/sudo/docker/compose,
                                   # creates ~/ubk, launches the shared registry
python bin/prod-dc-publish.py      # build + push images, upload the versioned compose file
python bin/prod-dc-up.py           # activate a version (down old, switch symlink, up, provision)
python bin/prod-dc-remove.py       # remove everything: containers, DATA, images, secrets
```

`--version` overrides `prod_version` on publish/up.

## How it works

Layout on the server:

```
~/ubk/<app>/
├── .env                          # secrets + PUBLIC_HOST (created on first publish)
├── docker-compose-<version>.yml  # one immutable file per published version
├── docker-compose.yml            # symlink to the active version
└── releases/<version>.sha256     # content hash guarding immutability
```

* **Registry** — a `registry:2` container (`ubk-registry`, shared by all apps)
  bound to the server's loopback `:5000`. `prod-dc-publish.py` pushes through an
  SSH tunnel; the server pulls from `localhost:5000/<app>/...`, so no image
  ever needs a public registry.
* **Immutable versions** — publish computes a content hash of everything that
  defines the release (compose file, image build inputs, frontend build).
  Re-publishing an existing version is a no-op if the content is identical and
  an **error** if it differs: bump `prod_version` (and regenerate) instead.
  For emergency/manual deployments, `python bin/prod-dc-publish.py --force`
  republishes the same version and overwrites its stored content hash.
* **Secrets** — Postgres password, JWT secret and the anon/service API keys are
  generated on the first publish and stored only in the server's
  `~/ubk/<app>/.env`. They survive version switches; `prod-dc-remove.py`
  deletes them.
* **Provisioning** — a one-shot `provision` container runs on every `up`: on
  the first activation it loads the schema, seed data, seed documents and auth
  users; afterwards it detects the marker table and only re-ensures the auth
  users exist. The `db-data` / `storage-data` volumes are reused by later
  versions (new versions do not reload schema or seed).
* **Frontend build** — the production anon key and public URL are baked into
  the SPA at `vite build` time; the app talks to Supabase through the nginx
  `<base_uri>/api` proxy (same-origin, like the Vite dev proxy).

## Operations

```bash
# First deployment
python bin/prod-dc-check-infra.py
python bin/prod-dc-publish.py
python bin/prod-dc-up.py

# New release: bump prod_version in deployment.jsonc, regenerate, then
python bin/prod-dc-publish.py && python bin/prod-dc-up.py

# Roll back to a previous version (data is kept as-is)
python bin/prod-dc-up.py --version <old>

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
  "prod_version": "v1",
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
