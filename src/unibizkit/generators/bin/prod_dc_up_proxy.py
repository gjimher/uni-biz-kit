from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Activate a published version of this proxy (Caddy) on the production server.

Target server and default version come from deployment_extended.json
(prod_dcd_ssh_srv, prod_version). The version must have been published with
bin/prod-dc-publish.py first. Idempotent.

Steps (all on the server, in ~/ubk/<app>):
  1. Verifies docker-compose-<version>.yml exists (else: publish first).
  2. If another version is active, takes it down (the caddy-data volume with the
     ACME certificates is NOT removed and is reused by the new version).
  3. Points the docker-compose.yml symlink at the requested version.
  4. `compose pull` + `compose up -d`.
  5. Checks the site answers over TLS on 443 and prints the public URL.
"""
import argparse
import sys
import time
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
domain = cfg["proxy"]["domain"]
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
print("Pulling image from the server registry...")
pc.ssh(srv, in_app + f"{compose} pull -q")
print("Starting Caddy...")
pc.ssh(srv, in_app + f"{compose} up -d")

# 5. TLS health check. On the first activation Caddy must obtain the certificate
# via ACME TLS-ALPN-01, which needs the public DNS A record -> NAT public IP ->
# port 443 forwarded to this host. Retry while that completes.
check = (
    "import socket, ssl, sys\\n"
    "ctx = ssl.create_default_context()\\n"
    "ctx.check_hostname = False\\n"
    "ctx.verify_mode = ssl.CERT_NONE\\n"
    "try:\\n"
    "    raw = socket.create_connection(('127.0.0.1', 443), timeout=10)\\n"
    f"    s = ctx.wrap_socket(raw, server_hostname='{domain}')\\n"
    f"    s.sendall(b'GET / HTTP/1.1\\\\r\\\\nHost: {domain}\\\\r\\\\nConnection: close\\\\r\\\\n\\\\r\\\\n')\\n"
    "    line = s.recv(64)\\n"
    "    s.close()\\n"
    "    sys.exit(0 if b' 200 ' in line else 1)\\n"
    "except Exception:\\n"
    "    sys.exit(1)\\n"
)
for attempt in range(24):
    if pc.remote_python(srv, check, check=False).returncode == 0:
        break
    time.sleep(5)
else:
    sys.exit(
        f"Error: {domain} did not answer with 200 over TLS on 443.\\n"
        f"Check `{compose} logs caddy` in {remote_dir} on {srv}. The ACME "
        "TLS-ALPN-01 challenge needs the DNS A record -> NAT public IP with "
        "port 443 forwarded to this host."
    )

print(f"\\n{pc.APP_ID} version {version} is up: https://{domain}/")
'''


def generate(bin_dir: Path):
    script = bin_dir / "prod-dc-up.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
