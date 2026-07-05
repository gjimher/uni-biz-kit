from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Activate a published version of this app on the production server.

Target server and default version come from deployment_extended.json
(prod_dcd_ssh_srv, prod_version). The version must have been published with
bin/prod-dc-publish.py first. Idempotent: re-activating the already-active
version just converges it to a running state.

Steps (all on the server, in ~/ubk/<app>):
  1. Verifies docker-compose-<version>.yml exists (else: publish first).
  2. If another version is active (docker-compose.yml symlink), takes it down
     (containers only — the db/storage data volumes are NOT removed and are
     reused by the new version).
  3. Points the docker-compose.yml symlink at the requested version.
  4. `compose pull` (images come from the registry on the server's loopback)
     and `compose up -d`.
  5. Waits for the one-shot provision container (schema/seed/users on first
     activation) and shows its logs; fails if it fails.
  6. Checks the frontend answers and prints the public URL.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prod_dc_common as pc

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("--version", help="Version to activate (default: prod_version from deployment_extended.json)")
args = parser.parse_args()

cfg = pc.deployment_config()
srv = cfg["prod_dcd_ssh_srv"]
version = args.version or cfg["prod_version"]
remote_dir = f"$HOME/{pc.REMOTE_APP_DIR}"
compose = pc.compose_cmd(srv)
in_app = f"cd {remote_dir} && "

# 1. Published?
if pc.ssh(srv, f"test -f {remote_dir}/docker-compose-{version}.yml", check=False).returncode != 0:
    sys.exit(f"Error: version {version} is not published on {srv}. "
             f"Run: python bin/prod-dc-publish.py --version {version}")

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
'''


def generate(bin_dir: Path):
    script = bin_dir / "prod-dc-up.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
