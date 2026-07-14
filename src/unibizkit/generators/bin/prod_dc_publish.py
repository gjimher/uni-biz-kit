from pathlib import Path


_CONTENT = r'''#!/usr/bin/python3
"""Publish this generated model without activating it.

The deployment policy comes from prod_versioning in deployment_extended.json:

  dev
    Builds and uploads the mutable dev artifact. A dirty Git worktree is
    accepted. The complete schema and seed data are packaged, but the running
    containers, database and Storage volume are not changed. A later
    prod-dc-up.py activation recreates the database and Storage from scratch.

  git-tag
    Requires a clean, attached Git worktree. The next model-scoped local tag is
    prod-<model>-vMAJOR.MINOR (minor is incremented by default). The generated
    complete schema is compared with the deployed database and the release
    packages only that Supabase migration. Compatible minor changes are allowed;
    destructive changes require --major --allow-destructive. The first release
    of a model (nothing deployed yet) packages the complete schema and skips
    the compatibility check, since there is no older artifact to protect.

Steps:
  1. Validates the deployment mode, Git state and requested release operation.
  2. Checks the production host and registry, creating app secrets if absent.
  3. In git-tag mode, compares the desired schema with the deployed database,
     rejects incompatible minor changes and verifies republication identity.
  4. Builds the frontend and version/commit-labelled Docker images.
  5. Pushes images through an SSH tunnel and uploads the versioned compose file,
     content hash, release manifest and migration.
  6. In git-tag mode, creates or moves the annotated local tag only after every
     publication step succeeds. Git remotes are never read or modified.

This command never applies SQL, stops containers, switches the active compose
file or removes volumes. Run prod-dc-up.py separately to activate the artifact.

Idempotency:
  Dev publication converges the mutable dev artifact to the current sources.
  Tagged publication always creates the next version. --republish replaces only
  the latest local candidate and only when its schema and normalized migration
  are identical to the previously published candidate. --dry-run performs the
  validations and schema comparison without changing Git, Docker or the server.
"""
import argparse
import hashlib
import json
import os
import socket
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prod_dc_common as pc
from prod_dc_release import (
    incompatible_migration_changes, migration_hash, next_version,
    tagged_versions, version_tag,
)

SUPABASE_CLI_VERSION = "2.88.1"

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("--dry-run", action="store_true", help="Validate and print actions without changing anything")
parser.add_argument("--major", action="store_true", help="Create the next major release")
parser.add_argument("--allow-destructive", action="store_true", help="Allow destructive changes in a major release")
parser.add_argument("--republish", action="store_true", help="Replace the latest local release if its migration is identical")
parser.add_argument("--tunnel-port", type=int, default=6543, help="Local port for the temporary production DB tunnel")
parser.add_argument("--registry-tunnel-port", type=int, default=5000,
                    help="Local port for the temporary registry tunnel (the remote side is always 5000)")
args = parser.parse_args()

cfg = pc.deployment_config()
mode = cfg["prod_versioning"]
srv = cfg["prod_dcd_ssh_srv"]
remote_dir = f"$HOME/{pc.REMOTE_APP_DIR}"


def command(argv, **kwargs):
    return pc.run([str(item) for item in argv], **kwargs)


def git(*argv, capture=True, check=True):
    return command(["git", "-C", pc.ROOT_DIR, *argv], capture=capture, check=check)


def local_tags():
    result = git("tag", "--list")
    return result.stdout.splitlines()


def head_sha():
    return git("rev-parse", "HEAD").stdout.strip()


def ensure_clean_git():
    if git("status", "--porcelain").stdout.strip():
        sys.exit("Error: git-tag deployments require a completely clean Git worktree.")
    if git("symbolic-ref", "-q", "HEAD", check=False).returncode != 0:
        sys.exit("Error: git-tag deployments are not allowed from a detached HEAD.")


def publish_artifact(version, *, force=False):
    """Build and upload one artifact without changing the active deployment."""
    env = None
    has_database = (pc.ROOT_DIR / "backend" / "supabase_schema.sql").exists()
    if has_database:
        env = pc.fetch_or_create_secrets(srv)
        frontend_dir = pc.ROOT_DIR / "frontend"
        if not (frontend_dir / "node_modules").exists():
            command(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend_dir)
        base_uri = cfg["base_uri"]
        prod_origin = (cfg.get("prod_origin") or "").rstrip("/")
        public_base = (
            f"{prod_origin}{base_uri}" if prod_origin
            else f"http://{env['PUBLIC_HOST']}:{cfg['prod_base_port']}{base_uri}"
        )
        command(["npm", "run", "build"], cwd=frontend_dir, env={
            **os.environ,
            "VITE_BASE_URL": public_base,
            "VITE_BASE_URI": base_uri,
            "VITE_SUPABASE_URL": f"{base_uri.rstrip('/')}/api",
            "VITE_SUPABASE_KEY": env["ANON_KEY"],
        })

    template = (pc.ROOT_DIR / "prod/docker/docker-compose.template.yml").read_text()
    compose_content = template.replace("__VERSION__", version).replace("__COMMIT__", head_sha())
    compose_file = pc.ROOT_DIR / "prod/docker" / f"docker-compose-{version}.yml"
    compose_file.write_text(compose_content)

    if has_database:
        vendor = json.loads((pc.ROOT_DIR / "prod/docker/vendor-images.json").read_text())
        build_specs = [
            ("db", "prod/docker/db/Dockerfile", "prod/docker/db"),
            ("kong", "prod/docker/kong/Dockerfile", "prod/docker/kong"),
            ("functions", "prod/docker/functions/Dockerfile", "."),
            ("provision", "prod/docker/provision/Dockerfile", "."),
            ("frontend", "prod/docker/frontend/Dockerfile", "."),
        ]
        hash_dirs = [
            "prod/docker/frontend", "prod/docker/db", "prod/docker/kong",
            "prod/docker/functions", "prod/docker/provision",
            "backend/supabase/functions", "frontend/dist",
        ]
        hash_files = [
            "prod/docker/vendor-images.json", "backend/supabase_schema.sql",
            "backend/release_migration.sql", "backend/supabase_seed_data_dev.sql",
            "backend/deployed_data_runtime.py", "security_extended.json", "seed_data_extended.json",
            "deployed_data_extended.json", "deployed_data_extended_schema.json", "concepts_extended.json",
        ]
    else:
        vendor = {}
        build_specs = [("caddy", "prod/docker/caddy/Dockerfile", ".")]
        hash_dirs = ["prod/docker/caddy"]
        hash_files = ["deployment_extended.json"]

    digest = pc.release_hash(compose_content, hash_dirs, hash_files)
    existing = pc.ssh(
        srv, f"cat {remote_dir}/releases/{version}.sha256 2>/dev/null",
        check=False, capture=True,
    )
    if existing.returncode == 0 and existing.stdout.strip() == digest and not force:
        print(f"Version {version} is already published with identical content; "
              "converging the registry and uploaded artifacts.")
    elif existing.returncode == 0 and existing.stdout.strip() and not force:
        sys.exit(f"Error: version {version} is already published with different content.")

    registry_port = args.registry_tunnel_port
    with socket.socket() as registry_probe:
        if registry_probe.connect_ex(("127.0.0.1", registry_port)) == 0:
            sys.exit(f"Error: local port {registry_port} is in use; "
                     "re-run with --registry-tunnel-port <free port>.")
    local_registry = f"localhost:{registry_port}"
    images = []
    for name, dockerfile, context in build_specs:
        image = f"{local_registry}/{pc.APP_ID}/{name}:{version}"
        command([
            "docker", "build", "-t", image,
            "--label", f"org.opencontainers.image.version={version}",
            "--label", f"org.opencontainers.image.revision={head_sha()}",
            "-f", pc.ROOT_DIR / dockerfile, pc.ROOT_DIR / context,
        ])
        images.append(image)
    for repo, source in vendor.items():
        if command(["docker", "image", "inspect", source], check=False, capture=True).returncode != 0:
            command(["docker", "pull", source])
        image = f"{local_registry}/{pc.APP_ID}/{repo}:{version}"
        command(["docker", "tag", source, image])
        images.append(image)

    tunnel = subprocess.Popen([
        "ssh", "-N", "-o", "BatchMode=yes",
        "-L", f"127.0.0.1:{registry_port}:127.0.0.1:5000", srv,
    ])
    try:
        for _ in range(30):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", registry_port)) == 0:
                    break
            time.sleep(0.5)
        else:
            sys.exit("Error: registry SSH tunnel did not start.")
        for image in images:
            command(["docker", "push", image])
    finally:
        tunnel.terminate()
        tunnel.wait()

    pc.ssh(srv, f"mkdir -p {remote_dir}/releases")
    command(["scp", "-q", compose_file, f"{srv}:{pc.REMOTE_APP_DIR}/docker-compose-{version}.yml"])
    pc.ssh(srv, f"cat > {remote_dir}/releases/{version}.sha256", input=digest + "\n")
    print(f"Published {pc.APP_ID}:{version}. Run: python bin/prod-dc-up.py")


def ensure_infra():
    if pc.ssh(srv, "test -d $HOME/ubk", check=False).returncode != 0 or not pc.registry_running(srv):
        sys.exit(f"Error: {srv} is not prepared. Run python bin/prod-dc-check-infra.py")


def publish_dev():
    if args.major or args.allow_destructive or args.republish:
        sys.exit("Error: --major, --allow-destructive and --republish only apply to git-tag mode.")
    print(f"Mode: dev; commit: {head_sha()}")
    has_database = (pc.ROOT_DIR / "backend" / "supabase_schema.sql").exists()
    if has_database:
        print("The artifact contains a complete schema and seeds; no database is changed by publish.")
    if args.dry_run:
        print("DRY RUN: build and upload the mutable :dev artifact without activating it.")
        return
    ensure_infra()
    publish_artifact("dev", force=True)
    schema_path = pc.ROOT_DIR / "backend/supabase_schema.sql"
    schema_sql = schema_path.read_text() if schema_path.exists() else ""
    metadata = json.dumps({
        "mode": "dev", "version": "dev", "commit": head_sha(),
        "schema_sha256": hashlib.sha256(schema_sql.encode()).hexdigest() if schema_sql else None,
    })
    pc.ssh(srv, f"mkdir -p {remote_dir}/releases && cat > {remote_dir}/releases/dev.json", input=metadata + "\n")
    print("Development artifact published. Run: python bin/prod-dc-up.py")


class Tunnel:
    def __init__(self, local_port):
        self.local_port = local_port
        self.process = None

    def __enter__(self):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", self.local_port)) == 0:
                sys.exit(f"Error: local tunnel port {self.local_port} is already in use.")
        self.process = subprocess.Popen([
            "ssh", "-N", "-o", "BatchMode=yes", "-L",
            f"127.0.0.1:{self.local_port}:127.0.0.1:{cfg['prod_base_port'] + 41}", srv,
        ])
        for _ in range(40):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", self.local_port)) == 0:
                    return self
            time.sleep(0.25)
        self.__exit__(None, None, None)
        sys.exit("Error: production database SSH tunnel did not start.")

    def __exit__(self, *_):
        if self.process:
            self.process.terminate()
            self.process.wait()


def db_url(password):
    from urllib.parse import quote
    return (
        f"postgresql://postgres:{quote(password, safe='')}@127.0.0.1:"
        f"{args.tunnel_port}/postgres?sslmode=require"
    )


def function_blocks(sql):
    blocks = []
    start = 0
    while True:
        match = re.search(r"CREATE OR REPLACE FUNCTION\b", sql[start:], re.IGNORECASE)
        if not match:
            return blocks
        begin = start + match.start()
        delimiter = re.search(r"\bAS\s+(\$[^$]*\$)", sql[begin:], re.IGNORECASE)
        if not delimiter:
            return blocks
        marker = delimiter.group(1)
        body_start = begin + delimiter.end()
        body_end = sql.find(marker, body_start)
        statement_end = sql.find(";", body_end + len(marker))
        if body_end < 0 or statement_end < 0:
            return blocks
        blocks.append(sql[begin:statement_end + 1])
        start = statement_end + 1


def catalog_fallback_diff(url, desired_sql):
    """Reconcile the public-schema constructs emitted by UniBizKit generators."""
    import psycopg2

    table_blocks = {}
    desired_columns = {}
    for match in re.finditer(r'CREATE TABLE "([^"]+)" \((.*?)\n\);', desired_sql, re.DOTALL):
        table, body = match.groups()
        table_blocks[table] = match.group(0) + ";"
        desired_columns[table] = {}
        for line in body.splitlines():
            column = re.match(r'\s*"([^"]+)"\s+(.+?)(?:,)?$', line)
            if column:
                desired_columns[table][column.group(1)] = column.group(2).removesuffix(",")

    desired_function_names = {
        match.group(1) or match.group(2)
        for match in re.finditer(
            r'CREATE OR REPLACE FUNCTION\s+(?:public\.)?(?:"([^"]+)"|([a-zA-Z_][\w]*))\s*\(',
            desired_sql, re.IGNORECASE,
        )
    }
    desired_policies = {
        (name, table)
        for name, table in re.findall(
            r'CREATE POLICY "([^"]+)" ON "([^"]+)"', desired_sql, re.IGNORECASE,
        )
    }
    desired_indexes = {
        match.group(1): match.group(0)
        for match in re.finditer(
            r'CREATE (?:UNIQUE )?INDEX "([^"]+)"[\s\S]*?;', desired_sql, re.IGNORECASE,
        )
    }

    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT c.table_name, c.column_name, "
            "pg_catalog.format_type(a.atttypid, a.atttypmod), c.is_nullable, c.column_default "
            "FROM information_schema.columns c "
            "JOIN pg_catalog.pg_class t ON t.relname = c.table_name "
            "JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace AND n.nspname = c.table_schema "
            "JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attname = c.column_name "
            "WHERE c.table_schema = 'public' AND c.table_name <> 'unibizkit_prod_releases'"
        )
        actual_rows = cur.fetchall()
        cur.execute(
            "SELECT p.proname, pg_get_function_identity_arguments(p.oid) "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public'"
        )
        actual_functions = cur.fetchall()
        cur.execute(
            "SELECT policyname, tablename FROM pg_policies WHERE schemaname = 'public'"
        )
        actual_policies = cur.fetchall()
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND indexname NOT LIKE '%_pkey'"
        )
        actual_indexes = dict(cur.fetchall())

    actual_columns = {}
    for table, column, data_type, nullable, default in actual_rows:
        actual_columns.setdefault(table, {})[column] = (data_type, nullable, default)

    statements = []
    for table in sorted(actual_columns.keys() - desired_columns.keys()):
        statements.append(f'DROP TABLE "{table}" CASCADE;')
    for table in sorted(desired_columns.keys() - actual_columns.keys()):
        statements.append(table_blocks[table])
    for table in sorted(desired_columns.keys() & actual_columns.keys()):
        for column in sorted(actual_columns[table].keys() - desired_columns[table].keys()):
            statements.append(f'ALTER TABLE "{table}" DROP COLUMN "{column}";')
        for column in sorted(desired_columns[table].keys() - actual_columns[table].keys()):
            statements.append(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" {desired_columns[table][column]};'
            )
        for column in sorted(desired_columns[table].keys() & actual_columns[table].keys()):
            desired_spec = desired_columns[table][column]
            desired_type = re.match(
                r'(DOUBLE PRECISION|TIMESTAMP WITH(?:OUT)? TIME ZONE|CHARACTER VARYING(?:\(\d+\))?|'
                r'VARCHAR(?:\(\d+\))?|NUMERIC(?:\([^)]*\))?|[A-Z][A-Z0-9_]*(?:\[\])?)',
                desired_spec, re.IGNORECASE,
            )
            actual_type, actual_nullable, actual_default = actual_columns[table][column]
            def normalized_type(value):
                value = value.lower().replace("varchar", "character varying")
                if value == "serial":
                    return "integer"
                if value == "bigserial":
                    return "bigint"
                return value

            if desired_type and normalized_type(desired_type.group(1)) != normalized_type(actual_type):
                dtype = desired_type.group(1)
                statements.append(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE {dtype} '
                    f'USING "{column}"::{dtype};'
                )
            wants_not_null = bool(re.search(r'\b(?:NOT NULL|PRIMARY KEY)\b', desired_spec, re.IGNORECASE))
            if wants_not_null != (actual_nullable == "NO"):
                action = "SET NOT NULL" if wants_not_null else "DROP NOT NULL"
                statements.append(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" {action};')
            desired_default = re.search(r'\bDEFAULT\s+(.+?)(?=\s+(?:NOT NULL|UNIQUE|REFERENCES|CHECK)\b|$)', desired_spec, re.IGNORECASE)
            if desired_default and actual_default is None:
                statements.append(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET DEFAULT {desired_default.group(1)};'
                )
            elif not desired_default and actual_default is not None and "SERIAL" not in desired_spec.upper():
                statements.append(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP DEFAULT;')

    for name, arguments in actual_functions:
        if name not in desired_function_names:
            statements.append(f'DROP FUNCTION public."{name}"({arguments}) CASCADE;')
    statements.extend(function_blocks(desired_sql))

    def normalized_index(definition):
        definition = definition.lower().replace('"', "")
        definition = definition.replace(" using btree ", " ")
        definition = re.sub(r"\bon\s+(?:only\s+)?public\.", "on ", definition)
        definition = re.sub(r"\s*,\s*", ", ", definition)
        return re.sub(r"\s+", " ", definition).strip().rstrip(";")

    # Rebuilding an index scans the whole table: keep indexes whose deployed
    # definition already matches; a normalization mismatch only costs a rebuild.
    for index in sorted(actual_indexes.keys() - desired_indexes.keys()):
        statements.append(f'DROP INDEX IF EXISTS "{index}";')
    for index in sorted(desired_indexes):
        actual = actual_indexes.get(index)
        if actual and normalized_index(actual) == normalized_index(desired_indexes[index]):
            continue
        statements.append(f'DROP INDEX IF EXISTS "{index}";')
        statements.append(desired_indexes[index])

    for name, table in actual_policies:
        statements.append(f'DROP POLICY IF EXISTS "{name}" ON "{table}";')
    statements.extend(
        match.group(0) for match in re.finditer(
            r'CREATE POLICY\b[\s\S]*?;', desired_sql, re.IGNORECASE,
        )
    )
    statements.extend(
        match.group(0) for match in re.finditer(
            r'DROP TRIGGER IF EXISTS[\s\S]*?;\s*CREATE TRIGGER[\s\S]*?;',
            desired_sql, re.IGNORECASE,
        )
    )
    statements.extend(
        match.group(0) for match in re.finditer(
            r'ALTER TABLE "[^"]+" ENABLE ROW LEVEL SECURITY;', desired_sql, re.IGNORECASE,
        )
    )
    statements.extend(
        match.group(0) for match in re.finditer(
            r'(?:GRANT|REVOKE)\b[\s\S]*?;', desired_sql, re.IGNORECASE,
        )
    )
    return "\n\n".join(statements) + ("\n" if statements else "")


def generate_diff(url, desired_sql):
    """Diff the deployed DB against a shadow DB built from the desired full schema."""
    operational_schema = """
CREATE TABLE IF NOT EXISTS public.unibizkit_prod_releases (
    version TEXT PRIMARY KEY,
    provisioned BOOLEAN NOT NULL DEFAULT false,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON public.unibizkit_prod_releases FROM anon, authenticated;
"""
    with tempfile.TemporaryDirectory(prefix="ubk-release-diff-") as tmp:
        root = Path(tmp)
        migrations = root / "supabase" / "migrations"
        migrations.mkdir(parents=True)
        (root / "supabase" / "config.toml").write_text(
            'project_id = "ubk_release_diff"\n'
            f'[db]\nport = {args.tunnel_port + 1}\n'
            f'shadow_port = {args.tunnel_port + 2}\nmajor_version = 17\n'
        )
        (migrations / "00000000000000_desired.sql").write_text(
            desired_sql + operational_schema
        )
        result = command([
            "npx", "-y", f"supabase@{SUPABASE_CLI_VERSION}", "db", "diff",
            "--from", url, "--to", "migrations", "--schema", "public", "--use-pg-schema",
        ], cwd=root, capture=True)
        sql = result.stdout
    if not sql.strip() or "No schema changes found" in sql:
        sql = catalog_fallback_diff(url, desired_sql)
    if not sql.strip():
        return "SELECT 1; -- schema already matches this release\n"
    return sql


def publish_git_tag():
    ensure_clean_git()
    versions = tagged_versions(pc.APP_ID, local_tags())
    if args.republish:
        if not versions:
            sys.exit("Error: there is no local release tag to republish.")
        version, tag = versions[-1]
    else:
        version = next_version(pc.APP_ID, local_tags(), major=args.major)
        tag = version_tag(pc.APP_ID, version)
    if args.allow_destructive and not args.major:
        sys.exit("Error: --allow-destructive is only valid together with --major.")
    print(f"Release: {tag}; commit: {head_sha()}")
    if not (pc.ROOT_DIR / "backend" / "supabase_schema.sql").exists():
        if args.dry_run:
            print("DRY RUN: publish a pending proxy artifact without activating it.")
            return
        ensure_infra()
        publish_artifact(str(version), force=args.republish)
        metadata = json.dumps({
            "mode": "git-tag", "version": str(version), "tag": tag,
            "commit": head_sha(), "republish": args.republish, "has_database": False,
        })
        pc.ssh(srv, f"cat > {remote_dir}/releases/{version}.json", input=metadata + "\n")
        if args.republish:
            git("tag", "-fa", tag, "-m", f"Publish {pc.APP_ID} {version}", capture=False)
        else:
            git("tag", "-a", tag, "-m", f"Publish {pc.APP_ID} {version}", capture=False)
        print(f"Published and tagged {tag}. Run: python bin/prod-dc-up.py")
        return
    ensure_infra()
    remote_compose = pc.ssh(srv, f"test -e {remote_dir}/docker-compose.yml", check=False).returncode == 0
    env = {}
    if remote_compose:
        if args.dry_run:
            env = pc.parse_env(pc.ssh_output(srv, f"cat {remote_dir}/.env 2>/dev/null || true"))
            if "POSTGRES_PASSWORD" not in env:
                sys.exit("Error: deployed database secrets are missing; cannot compare schemas.")
        else:
            env = pc.fetch_or_create_secrets(srv)
    schema_sql = (pc.ROOT_DIR / "backend" / "supabase_schema.sql").read_text()
    schema_digest = hashlib.sha256(schema_sql.encode()).hexdigest()
    # First release: the complete schema is applied by the provision container
    # on an empty database, so there is no older artifact to stay compatible with.
    sql = schema_sql
    reasons = []
    if remote_compose:
        active_compose = pc.ssh_output(srv, f"readlink {remote_dir}/docker-compose.yml 2>/dev/null || true")
        active_version = active_compose.removeprefix("docker-compose-").removesuffix(".yml")
        active_raw = pc.ssh_output(srv, f"cat {remote_dir}/releases/{active_version}.json 2>/dev/null || true")
        active_metadata = json.loads(active_raw or "{}")
        if active_metadata.get("schema_sha256") == schema_digest:
            sql = "SELECT 1; -- schema already matches this release\n"
        else:
            with Tunnel(args.tunnel_port):
                url = db_url(env["POSTGRES_PASSWORD"])
                sql = generate_diff(url, schema_sql)
        reasons = incompatible_migration_changes(sql)
        if reasons and not (args.major and args.allow_destructive):
            sys.exit("Error: incompatible minor migration:\n- " + "\n- ".join(reasons))
    digest = migration_hash(sql)
    if args.republish:
        raw = pc.ssh_output(srv, f"cat {remote_dir}/releases/{version}.json 2>/dev/null || true")
        previous = json.loads(raw or "{}")
        if (
            previous.get("migration_sha256") != digest
            or previous.get("schema_sha256") != schema_digest
        ):
            sys.exit("Error: republishing is only allowed when the migration is identical.")
    if args.dry_run:
        if remote_compose:
            print(f"DRY RUN: migration is compatible ({len(sql.encode())} bytes); publish and up were skipped.")
        else:
            print("DRY RUN: first release packages the complete schema; publish and up were skipped.")
        return
    migration_file = pc.ROOT_DIR / "backend" / "release_migration.sql"
    migration_file.write_text(sql)
    publish_artifact(str(version), force=args.republish)
    metadata = json.dumps({
        "mode": "git-tag", "has_database": True, "apply_migration": remote_compose,
        "version": str(version), "tag": tag, "commit": head_sha(),
        "migration_sha256": digest, "schema_sha256": schema_digest,
        "republish": args.republish, "destructive": bool(reasons),
    })
    pc.ssh(srv, f"cat > {remote_dir}/releases/{version}.sql", input=sql)
    pc.ssh(srv, f"cat > {remote_dir}/releases/{version}.json", input=metadata + "\n")
    if args.republish:
        git("tag", "-fa", tag, "-m", f"Publish {pc.APP_ID} {version}", capture=False)
    else:
        git("tag", "-a", tag, "-m", f"Publish {pc.APP_ID} {version}", capture=False)
    print(f"Published and tagged {tag}. Run: python bin/prod-dc-up.py")


if mode == "dev":
    publish_dev()
elif mode == "git-tag":
    publish_git_tag()
else:
    sys.exit(f"Error: unsupported prod_versioning value: {mode!r}")
'''


def generate(bin_dir: Path):
    # Remove files emitted by pre-unified deployment generators.
    old_script = bin_dir / "prod-dc-deploy.py"
    if old_script.exists():
        old_script.unlink()
    old_helper = bin_dir / "_prod_dc_publish_artifact.py"
    if old_helper.exists():
        old_helper.unlink()
    script = bin_dir / "prod-dc-publish.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
