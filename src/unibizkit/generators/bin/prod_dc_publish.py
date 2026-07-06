from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Build and publish an immutable release of this app to the production server.

Target server, base port and default version come from deployment_extended.json
(prod_dcd_ssh_srv, prod_base_port, prod_version). Requires the server to be
prepared once with bin/prod-dc-check-infra.py. This script only PUBLISHES; nothing
is (re)started — activate the version afterwards with bin/prod-dc-up.py.

Steps:
  1. Verifies the server is prepared (ssh + registry on remote 127.0.0.1:5000).
  2. Ensures the app secrets exist on the server (~/ubk/<app>/.env: postgres
     password, JWT secret, anon/service API keys, PUBLIC_HOST). They are
     generated on the first publish and reused forever after.
  3. Builds the frontend (npm install if needed + vite build) with the
     production anon key baked in.
  4. Renders prod/docker/docker-compose-<version>.yml from the template.
  5. Version immutability check against the content hash stored on the server:
     - version not yet published        -> continue
     - published with identical content -> success, nothing to do (idempotent)
     - published with different content -> ERROR (versions are immutable; bump
       prod_version or pass a new --version)
     Pass -f/--force to overwrite an existing version intentionally.
  6. Builds the app images (frontend, db, kong, functions, provision) and tags
     the vendor Supabase images, all under <registry>/<app>/...:<version>.
  7. Pushes them to the server registry through an SSH tunnel
     (localhost:<tunnel-port> -> server 127.0.0.1:5000).
  8. Uploads docker-compose-<version>.yml and the content hash to
     ~/ubk/<app>/ on the server.

Idempotent: a re-run of an unchanged, already-published version is a no-op.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prod_dc_common as pc

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("--version", help="Version to publish (default: prod_version from deployment_extended.json)")
parser.add_argument("--tunnel-port", type=int, default=5000,
                    help="Local port for the SSH tunnel to the remote registry (default: 5000)")
parser.add_argument("-f", "--force", action="store_true",
                    help="Republish this version even if it already exists")
args = parser.parse_args()

import json
import re

cfg = pc.deployment_config()
srv = cfg["prod_dcd_ssh_srv"]
version = args.version or cfg["prod_version"]
if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", version):
    sys.exit(f"Error: invalid version name {version!r}")

remote_dir = f"$HOME/{pc.REMOTE_APP_DIR}"
print(f"Publishing {pc.APP_ID} version {version} to {srv}")

# 1. Server prepared?
if pc.ssh(srv, "test -d $HOME/ubk", check=False).returncode != 0 or not pc.registry_running(srv):
    sys.exit(f"Error: {srv} is not prepared. Run: python bin/prod-dc-check-infra.py")

# 2. Secrets
env = pc.fetch_or_create_secrets(srv)

# 3. Frontend build
frontend_dir = pc.ROOT_DIR / "frontend"
if not (frontend_dir / "node_modules").exists():
    print("Installing frontend dependencies...")
    pc.run(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend_dir)
base_uri = cfg["base_uri"]
base_prefix = base_uri.rstrip("/")
prod_origin = (cfg.get("prod_origin") or "").rstrip("/")
if prod_origin:
    public_base = f"{prod_origin}{base_uri}"
else:
    public_base = f"http://{env['PUBLIC_HOST']}:{cfg['prod_base_port']}{base_uri}"
print("Building frontend (vite build)...")
pc.run(["npm", "run", "build"], cwd=frontend_dir, env={
    **os.environ,
    "VITE_BASE_URL": public_base,
    "VITE_BASE_URI": base_uri,
    "VITE_SUPABASE_URL": f"{base_prefix}/api",
    "VITE_SUPABASE_KEY": env["ANON_KEY"],
})

# 4. Render compose file
template = (pc.ROOT_DIR / "prod" / "docker" / "docker-compose.template.yml").read_text()
compose_content = template.replace("__VERSION__", version)
compose_file = pc.ROOT_DIR / "prod" / "docker" / f"docker-compose-{version}.yml"
compose_file.write_text(compose_content)
print(f"Rendered {compose_file.relative_to(pc.ROOT_DIR)}")

vendor = json.loads((pc.ROOT_DIR / "prod" / "docker" / "vendor-images.json").read_text())
app_repos = ["db", "kong", "functions", "provision", "frontend"] + list(vendor)


def registry_has_all_manifests():
    check = "import urllib.request, urllib.error, sys\\n"
    for repo_suffix in app_repos:
        check += (
            "req = urllib.request.Request("
            f"'http://127.0.0.1:5000/v2/{pc.APP_ID}/{repo_suffix}/manifests/{version}', "
            "headers={'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}, "
            "method='HEAD')\\n"
            "try:\\n"
            "    urllib.request.urlopen(req, timeout=10)\\n"
            "except Exception:\\n"
            "    sys.exit(1)\\n"
        )
    return pc.remote_python(srv, check, check=False).returncode == 0


# 5. Immutability check
digest = pc.release_hash(
    compose_content,
    [
        "prod/docker/frontend",
        "prod/docker/db",
        "prod/docker/kong",
        "prod/docker/functions",
        "prod/docker/provision",
        "backend/supabase/functions",
        "frontend/dist",
    ],
    [
        "prod/docker/vendor-images.json",
        "backend/supabase_schema.sql",
        "backend/supabase_seed_data_dev.sql",
        "security_extended.json",
        "seed_data_extended.json",
        "concepts_extended.json",
    ],
)
existing = pc.ssh(srv, f"cat {remote_dir}/releases/{version}.sha256 2>/dev/null",
                  check=False, capture=True)
if existing.returncode == 0 and existing.stdout.strip():
    if existing.stdout.strip() != digest:
        if not args.force:
            sys.exit(
                f"Error: version {version} is already published on {srv} with DIFFERENT content.\\n"
                "Published versions are immutable: bump prod_version in the model's "
                "deployment.jsonc (and regenerate), publish with --version <new>, "
                "or pass --force to overwrite this version."
            )
        print(f"WARNING: force-publishing existing version {version} with different content.")
    # Same content: only a no-op if the registry actually has every image.
    if registry_has_all_manifests():
        if args.force:
            print(f"WARNING: force-publishing existing version {version} even though content is identical.")
        else:
            print(f"Version {version} is already published with identical content. Nothing to do.")
            sys.exit(0)
    else:
        print(f"Version {version} is published but images are missing from the registry — re-pushing.")

# 6. Build / tag images
local_registry = f"localhost:{args.tunnel_port}"
builds = [
    ("db", "prod/docker/db/Dockerfile", "prod/docker/db"),
    ("kong", "prod/docker/kong/Dockerfile", "prod/docker/kong"),
    ("functions", "prod/docker/functions/Dockerfile", "."),
    ("provision", "prod/docker/provision/Dockerfile", "."),
    ("frontend", "prod/docker/frontend/Dockerfile", "."),
]
repos = []
for name, dockerfile, context in builds:
    tag = f"{local_registry}/{pc.APP_ID}/{name}:{version}"
    print(f"Building {tag} ...")
    pc.run(["docker", "build", "-t", tag,
            "-f", str(pc.ROOT_DIR / dockerfile), str(pc.ROOT_DIR / context)])
    repos.append(tag)

vendor = json.loads((pc.ROOT_DIR / "prod" / "docker" / "vendor-images.json").read_text())
for repo_suffix, source in vendor.items():
    if pc.run(["docker", "image", "inspect", source], check=False, capture=True).returncode != 0:
        print(f"Pulling {source} ...")
        pc.run(["docker", "pull", source])
    tag = f"{local_registry}/{pc.APP_ID}/{repo_suffix}:{version}"
    pc.run(["docker", "tag", source, tag])
    repos.append(tag)

# 7. Push through SSH tunnel
probe = socket.socket()
if probe.connect_ex(("127.0.0.1", args.tunnel_port)) == 0:
    probe.close()
    sys.exit(f"Error: local port {args.tunnel_port} is in use. Re-run with --tunnel-port <free port>.")
probe.close()
print(f"Opening SSH tunnel localhost:{args.tunnel_port} -> {srv}:127.0.0.1:5000 ...")
tunnel = subprocess.Popen(
    ["ssh", "-N", "-o", "BatchMode=yes",
     "-L", f"127.0.0.1:{args.tunnel_port}:127.0.0.1:5000", srv])
try:
    for _ in range(30):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", args.tunnel_port)) == 0:
                break
        time.sleep(0.5)
    else:
        sys.exit("Error: SSH tunnel did not come up.")
    for tag in repos:
        print(f"Pushing {tag} ...")
        pc.run(["docker", "push", tag])
finally:
    tunnel.terminate()
    tunnel.wait()

# 8. Upload compose file + content hash
pc.ssh(srv, f"mkdir -p {remote_dir}/releases")
pc.run(["scp", "-q", str(compose_file), f"{srv}:{pc.REMOTE_APP_DIR}/docker-compose-{version}.yml"])
pc.ssh(srv, f"cat > {remote_dir}/releases/{version}.sha256", input=digest + "\\n")

print(f"\\nPublished {pc.APP_ID}:{version} to {srv}.")
print(f"Activate it with: python bin/prod-dc-up.py --version {version}")
'''


def generate(bin_dir: Path):
    script = bin_dir / "prod-dc-publish.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
