from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Remove this proxy's production deployment completely from the server.

DESTRUCTIVE: removes the container, the caddy-data / caddy-config volumes (the
Let's Encrypt certificates and ACME account are LOST — the next deploy issues a
fresh certificate, mind the rate limits), the caddy image (on the docker daemon
and in the registry) and the whole ~/ubk/<app> directory. The shared
ubk-registry container and ~/ubk itself are left in place.

Target server comes from deployment_extended.json (prod_dcd_ssh_srv).
Idempotent: safe to run when nothing (or only part) is deployed.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prod_dc_common as pc

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("-f", "--force", action="store_true", help="Skip confirmation prompt")
args = parser.parse_args()

cfg = pc.deployment_config()
srv = cfg["prod_dcd_ssh_srv"]
remote_dir = f"$HOME/{pc.REMOTE_APP_DIR}"

if not args.force:
    answer = input(
        f"This removes {pc.APP_ID} from {srv}: container, TLS certificates "
        "(fresh Let's Encrypt issuance on the next deploy) and images. Are you sure? [y/N] "
    )
    if answer.strip().lower() != "y":
        print("Aborted.")
        sys.exit(0)

# 2. compose down -v (if a compose file is there)
if pc.ssh(srv, f"test -e {remote_dir}/docker-compose.yml", check=False).returncode == 0:
    compose = pc.compose_cmd(srv)
    print("Taking the stack down (container + volumes)...")
    pc.ssh(srv, f"cd {remote_dir} && {compose} down -v --remove-orphans", check=False)
else:
    print("No active compose file on the server.")

# 3. Remove app images from the docker daemon
print("Removing app images from the docker daemon...")
pc.ssh(srv,
       f"docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' "
       f"| grep '^{pc.REMOTE_REGISTRY}/{pc.APP_ID}/' "
       f"| xargs -r docker rmi -f",
       check=False)

# 4. Delete the app repositories from the registry + garbage-collect
print("Deleting app repositories from the registry...")
cleanup = f"""
import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:5000/v2"
PREFIX = "{pc.APP_ID}/"

def req(method, path, headers=None):
    r = urllib.request.Request(BASE + path, headers=headers or {{}}, method=method)
    return urllib.request.urlopen(r, timeout=30)

try:
    catalog = json.load(req("GET", "/_catalog?n=1000"))
except urllib.error.URLError as e:
    raise SystemExit(f"registry not reachable: {{e}}")
for repo in catalog.get("repositories") or []:
    if not repo.startswith(PREFIX):
        continue
    try:
        tags = json.load(req("GET", f"/{{repo}}/tags/list")).get("tags") or []
    except urllib.error.HTTPError:
        continue
    for tag in tags:
        try:
            resp = req("HEAD", f"/{{repo}}/manifests/{{tag}}",
                       {{"Accept": "application/vnd.docker.distribution.manifest.v2+json"}})
            digest = resp.headers["Docker-Content-Digest"]
            req("DELETE", f"/{{repo}}/manifests/{{digest}}")
            print(f"  deleted {{repo}}:{{tag}}")
        except urllib.error.HTTPError as e:
            print(f"  warning: could not delete {{repo}}:{{tag}}: {{e}}")
"""
pc.remote_python(srv, cleanup, check=False)
pc.ssh(srv,
       f"docker exec {pc.REGISTRY_CONTAINER} registry garbage-collect "
       "/etc/docker/registry/config.yml --delete-untagged >/dev/null 2>&1",
       check=False)
# The registry keeps an in-memory blob cache: after a GC it must be restarted,
# or later pushes skip re-uploading layers that no longer exist on disk.
pc.ssh(srv, f"docker restart {pc.REGISTRY_CONTAINER} >/dev/null", check=False)

# 5. Remove the app directory
pc.ssh(srv, f"rm -rf {remote_dir}")
print(f"\\nRemoved {pc.APP_ID} from {srv}.")
'''


def generate(bin_dir: Path):
    script = bin_dir / "prod-dc-remove.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
