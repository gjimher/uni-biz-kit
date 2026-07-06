from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Build and publish an immutable release of this proxy (Caddy) to production.

Target server and default version come from deployment_extended.json
(prod_dcd_ssh_srv, prod_version). Requires the server to be prepared once with
bin/prod-dc-check-infra.py. This script only PUBLISHES; activate the version
afterwards with bin/prod-dc-up.py.

Unlike an app publish, there is no frontend build, no vendor images and no
secrets: the release is a single Caddy image with the landing site and Caddyfile
baked in.

Steps:
  1. Verifies the server is prepared (ssh + registry on remote 127.0.0.1:5000).
  2. Renders prod/docker/docker-compose-<version>.yml from the template.
  3. Version immutability check against the content hash stored on the server
     (published-identical -> no-op; published-different -> error).
     Pass -f/--force to overwrite an existing version intentionally.
  4. Builds the caddy image under <registry>/<app>/caddy:<version>.
  5. Pushes it to the server registry through an SSH tunnel.
  6. Uploads docker-compose-<version>.yml and the content hash to ~/ubk/<app>/.

Idempotent: a re-run of an unchanged, already-published version is a no-op.
"""
import argparse
import json
import re
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

# 2. Render compose file
template = (pc.ROOT_DIR / "prod" / "docker" / "docker-compose.template.yml").read_text()
compose_content = template.replace("__VERSION__", version)
compose_file = pc.ROOT_DIR / "prod" / "docker" / f"docker-compose-{version}.yml"
compose_file.write_text(compose_content)
print(f"Rendered {compose_file.relative_to(pc.ROOT_DIR)}")


def registry_has_manifest():
    check = (
        "import urllib.request, sys\\n"
        "req = urllib.request.Request("
        f"'http://127.0.0.1:5000/v2/{pc.APP_ID}/caddy/manifests/{version}', "
        "headers={'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}, "
        "method='HEAD')\\n"
        "try:\\n"
        "    urllib.request.urlopen(req, timeout=10)\\n"
        "except Exception:\\n"
        "    sys.exit(1)\\n"
    )
    return pc.remote_python(srv, check, check=False).returncode == 0


# 3. Immutability check
digest = pc.release_hash(compose_content, ["prod/docker/caddy"])
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
    if registry_has_manifest():
        if args.force:
            print(f"WARNING: force-publishing existing version {version} even though content is identical.")
        else:
            print(f"Version {version} is already published with identical content. Nothing to do.")
            sys.exit(0)
    else:
        print(f"Version {version} is published but the image is missing from the registry — re-pushing.")

# 4. Build image
local_registry = f"localhost:{args.tunnel_port}"
tag = f"{local_registry}/{pc.APP_ID}/caddy:{version}"
print(f"Building {tag} ...")
pc.run(["docker", "build", "-t", tag,
        "-f", str(pc.ROOT_DIR / "prod/docker/caddy/Dockerfile"), str(pc.ROOT_DIR)])

# 5. Push through SSH tunnel
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
    print(f"Pushing {tag} ...")
    pc.run(["docker", "push", tag])
finally:
    tunnel.terminate()
    tunnel.wait()

# 6. Upload compose file + content hash
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
