from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Activate the latest published release or roll back to an explicit version.

Target server comes from deployment_extended.json. The version must have been
created with bin/prod-dc-publish.py first. Idempotent: re-activating the already-active
version just converges it to a running state.

Steps (all on the server, in ~/ubk/<app>):
  1. Selects dev/latest local tag and verifies its remote manifest and artifact.
  2. For a pending destructive migration, creates and validates a backup.
  3. Applies the release migration through Supabase, if it is not already applied.
  4. If another version is active (docker-compose.yml symlink), takes it down
     (containers only — the db/storage data volumes are NOT removed and are
     reused by the new version).
  5. Points docker-compose.yml at the selected version and starts it.
  6. `compose pull` (images come from the registry on the server's loopback)
     and `compose up -d`.
  7. Waits for the one-shot provision container (schema/seed/users on first
     activation) and shows its logs; fails if it fails.
  8. Checks the frontend answers and prints the public URL.
"""
import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prod_dc_common as pc
from prod_dc_release import migration_hash, tagged_versions

SUPABASE_CLI_VERSION = "2.88.1"

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("--version", help="Previously published version to activate (rollback)")
parser.add_argument("--force", action="store_true", help="Skip the destructive dev confirmation")
parser.add_argument("--tunnel-port", type=int, default=6543, help="Local port for the production DB tunnel")
args = parser.parse_args()

cfg = pc.deployment_config()
srv = cfg["prod_dcd_ssh_srv"]
remote_dir = f"$HOME/{pc.REMOTE_APP_DIR}"
compose = pc.compose_cmd(srv)
in_app = f"cd {remote_dir} && "
normal_activation = args.version is None

def command(argv, **kwargs):
    return pc.run([str(item) for item in argv], **kwargs)


class Tunnel:
    def __enter__(self):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", args.tunnel_port)) == 0:
                sys.exit(f"Error: local tunnel port {args.tunnel_port} is already in use.")
        self.process = subprocess.Popen([
            "ssh", "-N", "-o", "BatchMode=yes", "-L",
            f"127.0.0.1:{args.tunnel_port}:127.0.0.1:{cfg['prod_base_port'] + 41}", srv,
        ])
        for _ in range(40):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", args.tunnel_port)) == 0:
                    return self
            time.sleep(0.25)
        self.__exit__(None, None, None)
        sys.exit("Error: production database SSH tunnel did not start.")

    def __exit__(self, *_):
        self.process.terminate()
        self.process.wait()


def db_url(password):
    from urllib.parse import quote
    return (
        f"postgresql://postgres:{quote(password, safe='')}@127.0.0.1:"
        f"{args.tunnel_port}/postgres?sslmode=require"
    )


def apply_migration(url, release_version, sql):
    version_obj = next(v for v, _ in tagged_versions(pc.APP_ID, [f"prod-{pc.APP_ID}-{release_version}"]))
    migration_id = f"{version_obj.major:07d}{version_obj.minor:07d}"
    with tempfile.TemporaryDirectory(prefix="ubk-release-push-") as tmp:
        root = Path(tmp)
        migrations = root / "supabase/migrations"
        migrations.mkdir(parents=True)
        (root / "supabase/config.toml").write_text('project_id = "ubk_release_push"\\n')
        fetched = command([
            "npx", "-y", f"supabase@{SUPABASE_CLI_VERSION}", "migration", "fetch", "--db-url", url,
        ], cwd=root, check=False, capture=True)
        (migrations / f"{migration_id}_release.sql").write_text(sql)
        if fetched.returncode == 0:
            command(["npx", "-y", f"supabase@{SUPABASE_CLI_VERSION}", "migration", "list", "--db-url", url], cwd=root)
        command([
            "npx", "-y", f"supabase@{SUPABASE_CLI_VERSION}", "db", "push",
            "--db-url", url, "--include-all", "--yes",
        ], cwd=root)


def backup_database(release_version):
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    path = f"{remote_dir}/backups/pre-{release_version}-{stamp}.dump"
    backup = (
        f"mkdir -p {remote_dir}/backups && cd {remote_dir} && "
        f"{compose} exec -T db pg_dump -U supabase_admin -Fc postgres > {path} && "
        f"{compose} exec -T db pg_restore -l < {path} >/dev/null"
    )
    pc.ssh(srv, backup)
    print(f"Validated backup: {srv}:{path}")


metadata = None
if cfg["prod_versioning"] == "git-tag":
    versions = tagged_versions(pc.APP_ID, pc.run([
        "git", "-C", pc.ROOT_DIR, "tag", "--list",
    ], capture=True).stdout.splitlines())
    if not versions:
        sys.exit("Error: no published local release tag. Run python bin/prod-dc-publish.py first.")
    if args.version:
        matches = [(item, tag) for item, tag in versions if str(item) == args.version]
        if not matches:
            sys.exit(f"Error: {args.version} is not a local release of {pc.APP_ID}.")
        version_obj, tag = matches[-1]
    else:
        version_obj, tag = versions[-1]
    version = str(version_obj)
    raw = pc.ssh_output(srv, f"cat {remote_dir}/releases/{version}.json 2>/dev/null || true")
    if not raw:
        sys.exit(f"Error: release metadata for {version} is missing on {srv}.")
    metadata = json.loads(raw)
    tag_commit = pc.run([
        "git", "-C", pc.ROOT_DIR, "rev-list", "-n", "1", tag,
    ], capture=True).stdout.strip()
    if metadata.get("tag") != tag or metadata.get("commit") != tag_commit:
        sys.exit(f"Error: local tag {tag} does not match the published artifact metadata.")
else:
    version = args.version or "dev"

# 1. Published?
if pc.ssh(srv, f"test -f {remote_dir}/docker-compose-{version}.yml", check=False).returncode != 0:
    sys.exit(f"Error: version {version} is not published on {srv}. "
             "Run: python bin/prod-dc-publish.py")

if normal_activation and cfg["prod_versioning"] == "dev":
    dev_raw = pc.ssh_output(srv, f"cat {remote_dir}/releases/dev.json 2>/dev/null || true")
    if not dev_raw:
        sys.exit("Error: dev is not published. Run python bin/prod-dc-publish.py first.")
    if not args.force:
        answer = input("All production data and uploaded documents will be lost. Continue? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)
    if pc.ssh(srv, f"test -e {remote_dir}/docker-compose.yml", check=False).returncode == 0:
        pc.ssh(srv, in_app + f"{compose} down -v --remove-orphans")

if normal_activation and metadata and metadata.get("has_database") and metadata.get("apply_migration"):
    sql = pc.ssh_output(srv, f"cat {remote_dir}/releases/{version}.sql")
    if migration_hash(sql) != metadata.get("migration_sha256"):
        sys.exit(f"Error: migration hash for {version} does not match its release metadata.")
    migration_id = f"{version_obj.major:07d}{version_obj.minor:07d}"
    migration_status = pc.ssh(
        srv,
        in_app + f"{compose} exec -T db psql -At -U postgres postgres "
        f"-c 'SELECT EXISTS (SELECT 1 FROM supabase_migrations.schema_migrations "
        f"WHERE version = $${migration_id}$$)'",
        check=False, capture=True,
    )
    applied = migration_status.returncode == 0 and migration_status.stdout.strip() == "t"
    if not applied:
        if metadata.get("destructive"):
            backup_database(version)
        env = pc.fetch_or_create_secrets(srv)
        with Tunnel():
            apply_migration(db_url(env["POSTGRES_PASSWORD"]), version, sql)
    else:
        print(f"Migration {migration_id} is already applied.")

# 2./3. Switch the active version
current = pc.ssh_output(srv, f"readlink {remote_dir}/docker-compose.yml 2>/dev/null || true")
target = f"docker-compose-{version}.yml"
if current and current != target:
    print(f"Stopping active version ({current}) ...")
    pc.ssh(srv, in_app + f"{compose} down")
pc.ssh(srv, in_app + f"ln -sfn {target} docker-compose.yml")
print(f"Active version: {version}")

# 4. Pull + up
print("Pulling images from the server registry...")
pc.ssh(srv, in_app + f"{compose} pull -q")
print("Starting the stack...")
pc.ssh(srv, in_app + f"{compose} up -d")

# 5. Wait for provision
print("Waiting for the provision container to finish...")
cid = pc.ssh_output(srv, in_app + f"{compose} ps -q provision")
if not cid:
    sys.exit("Error: provision container not found.")
exit_code = pc.ssh_output(srv, f"docker wait {cid}")
pc.ssh(srv, f"docker logs {cid} 2>&1 | tail -40", check=False)
if exit_code != "0":
    sys.exit(f"Error: provision failed with exit code {exit_code} (full logs: docker logs {cid} on {srv}).")

# 6. Frontend check
port = cfg["prod_base_port"]
base_uri = cfg["base_uri"]
check = (
    "import urllib.request, sys\\n"
    f"status = urllib.request.urlopen('http://127.0.0.1:{port}{base_uri}', timeout=15).status\\n"
    "sys.exit(0 if status == 200 else 1)\\n"
)
if pc.remote_python(srv, check, check=False).returncode != 0:
    sys.exit(f"Error: frontend does not answer on port {port} "
             f"(check `{compose} ps` and `{compose} logs` in {remote_dir} on {srv}).")

host = pc.parse_env(pc.ssh_output(srv, f"cat {remote_dir}/.env")).get("PUBLIC_HOST") or pc.remote_host(srv)
print(f"\\n{pc.APP_ID} version {version} is up: http://{host}:{port}{base_uri}")

if normal_activation and cfg["prod_versioning"] == "dev":
    pc.ssh(srv, "docker image prune -f >/dev/null", check=False)
    pc.ssh(
        srv,
        f"docker exec {pc.REGISTRY_CONTAINER} registry garbage-collect "
        "/etc/docker/registry/config.yml --delete-untagged >/dev/null 2>&1",
        check=False,
    )
    pc.ssh(srv, f"docker restart {pc.REGISTRY_CONTAINER} >/dev/null", check=False)
    print("Development activation complete; database and storage were recreated.")
'''


def generate(bin_dir: Path):
    script = bin_dir / "prod-dc-up.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
