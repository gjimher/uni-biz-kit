from .constants import IMAGES


def frontend(ctx) -> str:
    """nginx serving the built SPA; build context is the app output root."""
    html_dir = f"/usr/share/nginx/html{ctx.base_prefix}"
    return f"""\
FROM {IMAGES['nginx']}
COPY prod/docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/dist/ {html_dir}/
"""


def db() -> str:
    """Supabase Postgres with the self-hosting init scripts baked in.

    The image already ships the Supabase roles and schemas; the init scripts
    only set the role passwords and the JWT database settings (same files the
    official self-hosting compose mounts). Build context: prod/docker/db.
    """
    return f"""\
FROM {IMAGES['nginx']} AS tls
RUN apk add --no-cache openssl \
 && openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
      -subj "/CN=unibizkit-postgres" \
      -keyout /tmp/ubk-db.key -out /tmp/ubk-db.crt

FROM {IMAGES['db']}
COPY --from=tls /tmp/ubk-db.key /etc/ssl/private/ubk-db.key
COPY --from=tls /tmp/ubk-db.crt /etc/ssl/certs/ubk-db.crt
RUN chown postgres:postgres /etc/ssl/private/ubk-db.key /etc/ssl/certs/ubk-db.crt \
 && chmod 600 /etc/ssl/private/ubk-db.key
COPY init-scripts/ /docker-entrypoint-initdb.d/init-scripts/
"""


def db_roles_sql() -> str:
    # Init runs with ON_ERROR_STOP, so each ALTER is guarded: the role set
    # varies between supabase/postgres image versions.
    return """\
-- Set the service role passwords from POSTGRES_PASSWORD (runs only on first init).
\\set pgpass `echo "$POSTGRES_PASSWORD"`
-- psql does not interpolate :vars inside dollar-quoted bodies: pass it via a GUC.
SELECT set_config('ubk.pgpass', :'pgpass', false);

DO $$
DECLARE
    role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'postgres', 'authenticator', 'supabase_auth_admin',
        'supabase_functions_admin', 'supabase_storage_admin', 'pgbouncer'
    ] LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('ALTER USER %I WITH PASSWORD %L',
                           role_name, current_setting('ubk.pgpass'));
        END IF;
    END LOOP;
END $$;
"""


def db_jwt_sql() -> str:
    return """\
-- Expose the JWT settings as database settings (used by RLS helpers and pg_net triggers).
\\set jwt_secret `echo "$JWT_SECRET"`
\\set jwt_exp `echo "$JWT_EXP"`

ALTER DATABASE postgres SET "app.settings.jwt_secret" TO :'jwt_secret';
ALTER DATABASE postgres SET "app.settings.jwt_exp" TO :'jwt_exp';
"""


def db_ownership_sql() -> str:
    """The image pre-creates the auth/storage schemas with some objects owned
    by postgres; GoTrue and Storage then fail to run their own migrations as
    supabase_auth_admin / supabase_storage_admin ('must be owner of ...').
    Hand every object over to the service admin roles (what the Supabase CLI
    ends up with in dev)."""
    return """\
-- Transfer auth/storage schema objects to their service admin roles so the
-- GoTrue and Storage migrations (running as those roles) can alter them.
DO $$
DECLARE
    spec RECORD;
    obj RECORD;
BEGIN
    FOR spec IN
        SELECT * FROM (VALUES
            ('auth', 'supabase_auth_admin'),
            ('storage', 'supabase_storage_admin')
        ) AS s(schema_name, role_name)
    LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = spec.role_name)
           OR NOT EXISTS (SELECT FROM pg_namespace WHERE nspname = spec.schema_name) THEN
            CONTINUE;
        END IF;
        EXECUTE format('GRANT USAGE, CREATE ON SCHEMA %I TO %I', spec.schema_name, spec.role_name);
        FOR obj IN SELECT tablename AS name FROM pg_tables WHERE schemaname = spec.schema_name LOOP
            EXECUTE format('ALTER TABLE %I.%I OWNER TO %I', spec.schema_name, obj.name, spec.role_name);
        END LOOP;
        FOR obj IN SELECT sequencename AS name FROM pg_sequences WHERE schemaname = spec.schema_name LOOP
            EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO %I', spec.schema_name, obj.name, spec.role_name);
        END LOOP;
        FOR obj IN
            SELECT p.proname AS name, pg_get_function_identity_arguments(p.oid) AS args
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = spec.schema_name
        LOOP
            EXECUTE format('ALTER FUNCTION %I.%I(%s) OWNER TO %I',
                           spec.schema_name, obj.name, obj.args, spec.role_name);
        END LOOP;
    END LOOP;
END $$;
"""


def kong() -> str:
    """Kong with the declarative config template baked in; the compose
    entrypoint substitutes the API keys at container start.
    Build context: prod/docker/kong."""
    return f"""\
FROM {IMAGES['kong']}
COPY temp.yml /home/kong/temp.yml
"""


def functions() -> str:
    """Edge runtime with an offline Deno cache and the main router baked in.

    Build context is the app output root (needs backend/supabase/functions).
    """
    return f"""\
FROM denoland/deno:2.1.4 AS dependencies
USER root
WORKDIR /functions
COPY backend/supabase/functions/ ./
RUN set -eu; \
    find . -mindepth 2 -maxdepth 2 -name index.ts -print | sort | \
    while read -r entrypoint; do \
      directory="$(dirname "${{entrypoint}}")"; \
      (cd "${{directory}}" && deno install --entrypoint index.ts); \
    done
RUN set -eu; \
    find . -mindepth 2 -maxdepth 2 -name index.ts -print | sort | \
    while read -r entrypoint; do \
      directory="$(dirname "${{entrypoint}}")"; \
      (cd "${{directory}}" && deno install --cached-only --entrypoint index.ts); \
    done

FROM {IMAGES['edge_runtime']}
ENV DENO_DIR=/deno-dir/
COPY --from=dependencies /deno-dir/ /deno-dir/
COPY --from=dependencies /functions/ /home/deno/functions/
COPY prod/docker/functions/main/ /home/deno/functions/main/
"""


def provision() -> str:
    """One-shot provisioner; build context is the app output root."""
    return f"""\
FROM {IMAGES['python']}
RUN pip install --no-cache-dir psycopg2-binary
WORKDIR /app
COPY backend/supabase_schema.sql backend/supabase_seed_data_dev.sql ./
COPY backend/release_migration.sql* ./
COPY security_extended.json seed_data_extended.json concepts_extended.json ./
COPY prod/docker/provision/provision.py ./
CMD ["python", "provision.py"]
"""
