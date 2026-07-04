# Development Guide

How to work on UniBizKit itself and on application models. For first-time setup see [USAGE.md](USAGE.md); for what gets generated see [Backend.md](Backend.md) and [Frontend.md](Frontend.md).

## Test-driven generation

The test suite runs against the `models/test-app` model: `pytest` regenerates the code, deploys it and verifies it. Do not run `uni-biz-kit` by hand during development — change the generators, run `pytest`, and inspect the output in `test-app/`.

When developing your own model, set `UBK_DEV_MODEL` (the repo's `.envrc` sets it to `b2c-app` via direnv) so that `pytest` generates and verifies **both** models, each on its own ports (see [below](#second-dev-environment-ubk_dev_model)).

## One Supabase instance per model

Each model gets its own Supabase instance, in dev and in production. This avoids monoliths, keeps models decoupled and makes deployment straightforward (see [Architecture.md](Architecture.md#one-supabase-instance-per-model)). The `bin/dev-*` scripts below operate the instance of the app they live in.

## Dev scripts (`<app>/bin/dev-*`)

Every generated app ships scripts to operate its local stack. The state-changing scripts (`start`, `stop`, `remove`) are [idempotent](Architecture.md#idempotent-operations): re-running them just converges to the requested state. This is the summary — the detail for each script is in its `-h`:

| Script | What it does |
|--------|--------------|
| `dev-supabase-start.py` | Creates/starts the app's Supabase instance; writes `backend/.env` with URL and keys |
| `dev-supabase-stop.py` | Stops the instance (idempotent, data preserved) |
| `dev-supabase-remove.py` | Stops and removes the instance |
| `dev-supabase-reset-schema-and-data.py` | Resets the database to the generated schema and seed data |
| `dev-supabase-call-edge-function.py` | Calls an [edge function](Backend.md#edge-functions) authenticated as a given user |
| `dev-smtp-mock.py` | SMTP mock: captures auth emails and prints them (with their links) to stdout |
| `dev-sso-start.py` | Starts and auto-configures the [SSO](SingleSignOn.md) dev environment (Kerberos + Keycloak) |
| `dev-sso-stop.py` | Stops the SSO containers, keeping volumes |
| `dev-sso-remove.py` | Stops and removes the SSO environment |
| `dev-sso-chrome.py` | Gets a Kerberos ticket and launches Chrome for SSO login |

The `dev-sso-*` scripts are only generated when the model enables [SSO](SingleSignOn.md).

## Multiple dev environments on one machine

Set `UBK_DEV_ENV_NUM` before running any generator command or test suite to select an isolated environment. If the variable is absent or `0`, you get the default environment.

```bash
export UBK_DEV_ENV_NUM=1   # env 1 — all ports shift by 100
pytest                     # generates and tests env 1
```

All ports for a given environment are derived from a single base:

```
base = 3000 + 100 * UBK_DEV_ENV_NUM   (+50 for the UBK_DEV_MODEL)
```

Each `UBK_DEV_ENV_NUM` block of 100 ports hosts **two** parallel environments: the
primary model (`models/test-app`) at offset `0` (`base+0..49`) and the
[second dev environment](#second-dev-environment-ubk_dev_model) (`UBK_DEV_MODEL`)
at offset `50` (`base+50..99`). The generator applies the `+50` automatically when
the model it is generating matches `UBK_DEV_MODEL` — there is no separate offset
variable.

### Port table

| Offset | Env 0 | Env 1 | Service |
|--------|-------|-------|---------|
| base+0  | 3000 | 3100 | React dev server (Vite) |
| base+1  | 3001 | 3101 | Vite preview (E2E tests) |
| base+2  | 3002 | 3102 | Chrome remote debugging (SSO) |
| base+3  | 3003 | 3103 | Edge Runtime inspector (Deno) |
| base+10 | 3010 | 3110 | SMTP mock |
| base+30 | 3030 | 3130 | Keycloak web (SSO) |
| base+31 | 3031 | 3131 | Keycloak management |
| base+32 | 3032 | 3132 | KDC (Kerberos) |
| base+33 | 3033 | 3133 | Kadmin (Kerberos) |
| base+40 | 3040 | 3140 | Supabase API |
| base+41 | 3041 | 3141 | Supabase DB (PostgreSQL) |
| base+42 | 3042 | 3142 | Supabase shadow DB (migrations) |
| base+43 | 3043 | 3143 | Supabase Studio |
| base+44 | 3044 | 3144 | Supabase Inbucket (email UI) |
| base+45 | 3045 | 3145 | Supabase Analytics |
| base+46 | 3046 | 3146 | Supabase Pooler (PgBouncer) |

The second environment (`UBK_DEV_MODEL`) mirrors this exact layout shifted by
`+50` (e.g. its Vite dev server is `base+50`, its Supabase API `base+90`, its
Supabase DB `base+91`).

### Container naming

Docker containers are automatically namespaced per environment using a two-digit suffix (`NN = UBK_DEV_ENV_NUM` zero-padded).

- **Supabase** — the `project_id` in `supabase_config_dev.toml` becomes `{app_name}_{NN}` (e.g. `test_app_00`, `test_app_01`). Supabase CLI prefixes all containers with this id.
- **SSO (docker-compose)** — the Compose project is `unibizkit-sso-{NN}`; containers are named `kdc_{NN}` and `keycloak_{NN}`; volumes are `kdc-data-{NN}`, `keytabs-{NN}`, `keycloak-data-{NN}`; the internal network is `sso-net-{NN}`; the local KDC image is `unibizkit-sso-kdc-{NN}:latest`.

### Central port definition

All port numbers are computed in `src/unibizkit/generators/dev_ports.py`. Edit that file to adjust the layout. Generators read it at generation time; the CLI calls `dev_ports.set_secondary(True)` (shifting everything by `+50`) when the model being generated matches `UBK_DEV_MODEL`.

---

## Second dev environment (`UBK_DEV_MODEL`)

Alongside the primary `models/test-app` environment, the test suite generates and
launches a **second** app on the `+50` port offset, so two full stacks (each with
its own Supabase, frontend and ports) run side by side within the same
`UBK_DEV_ENV_NUM` block.

**`UBK_DEV_MODEL`** — name of the model loaded into the second environment.
Defaults to `test-dummy-app` (a minimal smoke-test model under `models/`). The CLI
applies the `+50` port offset when the model it generates matches this name (see
`generate_secondary_model()` in `tests/conftest.py`); the second model is generated
in a subprocess to keep it cleanly separated from the primary in-process generation.
The Supabase `project_id` embeds the app name, so the two stacks get distinct Docker
containers (`test_app_NN` vs `dummy_app_NN`) and coexist without collisions.

### What the test suite does for the second environment

| File | Added coverage |
|------|----------------|
| `tests/test_backend.py` | Generates the second model, brings up its Supabase, resets schema/seed, and verifies its Postgres responds. |
| `tests/test_frontend.py` | Generates the second model's frontend and runs `npm run build`. |
| `tests/test_e2e.py`     | Builds and serves the second frontend on `base+51` and asserts it answers HTTP 200 (`--slow`). |

### App vs. tests: who talks to Supabase, and how

The generated app talks to Supabase **through the Vite `/api` proxy**, same-origin.
`frontend/.env.development` sets `VITE_SUPABASE_URL` to a **relative** path
(`/<base>/api`, no host or port); the app resolves it against `window.location.origin`,
so it works on whatever server serves it. Both the dev server (`npm start`, via
`server.proxy`) and `vite preview` (via `preview.proxy`) forward `/<base>/api` → Kong,
so the E2E tests need a single server and never start a second one. `supabase start`
keeps `[api].external_url` pointed at the proxy too, so auth email links stay
same-origin.

Tests and dev tooling, on the other hand, reach Supabase **directly at Kong** and do
not depend on a running dev server. `dev-supabase-start.py` writes the direct URL and
keys to `backend/.env` (`SUPABASE_URL` = `http://localhost:<base+40>`, plus
`SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`); the test suite and the `reset` /
`call-edge-function` scripts read `backend/.env`. Email links in tests are spliced
onto the Kong URL (`_normalize_confirmation_url` in `tests/test_api_auth.py`).

### Cold start without a dev server

Because `[api].external_url` is the Vite proxy, a **cold** `supabase start` would try
to verify storage through it and roll the stack back with a `connection refused` on
`…/storage/v1/bucket` when no dev server is running. To make a cold start
self-sufficient, `dev-supabase-start.py` brings up a tiny stdlib `/api`→Kong proxy on
the frontend port **only for the duration of `supabase start`**, and only if that port
is free (a real dev server takes precedence). Nothing else needs the proxy: reset and
the tests already hit Kong directly.

---


