from pathlib import Path

_CONTENT = '''\
#!/usr/bin/python3
"""Check and prepare the production server for docker-compose deployments.

Target server: prod_dcd_ssh_srv in deployment_extended.json (an ssh alias or
user@host; the user needs sudo and docker installed). Idempotent: run it as
many times as you want; it only needs to succeed once before the first
bin/prod-dc-publish.py.

Checks / prepares, in order:
  1. SSH connectivity (BatchMode: keys must be set up, no password prompts).
  2. Passwordless sudo (sudo -n true).
  3. Docker daemon access for the ssh user (docker version).
  4. A compose implementation: 'docker compose' plugin or classic 'docker-compose'.
  5. Creates ~/ubk on the server if missing (root of all UniBizKit deployments).
  6. Launches the shared docker registry container 'ubk-registry' (registry:2,
     bound to the server loopback 127.0.0.1:5000, restart unless-stopped, data
     in the ubk-registry volume, deletions enabled so prod-dc-remove.py can clean
     up). Starts it if it exists but is stopped; leaves it alone if running.
  7. Verifies the registry answers on http://127.0.0.1:5000/v2/.

Exits non-zero with a diagnostic on the first failed check.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prod_dc_common as pc

argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
).parse_args()

srv = pc.deployment_config()["prod_dcd_ssh_srv"]
print(f"Production server: {srv} ({pc.remote_host(srv)})")

# 1. SSH
if pc.ssh(srv, "true", check=False).returncode != 0:
    sys.exit(f"Error: cannot ssh to {srv!r} non-interactively. "
             "Check ~/.ssh/config and that your key is authorized.")
print("OK: ssh access")

# 2. sudo
if pc.ssh(srv, "sudo -n true", check=False).returncode != 0:
    sys.exit(f"Error: user has no passwordless sudo on {srv}.")
print("OK: passwordless sudo")

# 3. docker
result = pc.ssh(srv, "docker version --format '{{.Server.Version}}'", check=False, capture=True)
if result.returncode != 0:
    sys.exit(f"Error: docker not usable by the ssh user on {srv} "
             "(is docker installed and the user in the docker group?).")
print(f"OK: docker {result.stdout.strip()}")

# 4. compose
print(f"OK: compose available as '{pc.compose_cmd(srv)}'")

# 5. ~/ubk
pc.ssh(srv, "mkdir -p $HOME/ubk")
print("OK: ~/ubk exists")

# 6. registry container
state = pc.ssh_output(
    srv, f"docker inspect -f '{{{{.State.Running}}}}' {pc.REGISTRY_CONTAINER} 2>/dev/null || echo absent",
    check=False)
if state == "absent":
    print("Launching registry container...")
    pc.ssh(srv,
           f"docker run -d --name {pc.REGISTRY_CONTAINER} --restart unless-stopped "
           f"-p 127.0.0.1:5000:5000 -e REGISTRY_STORAGE_DELETE_ENABLED=true "
           f"-v ubk-registry:/var/lib/registry registry:2")
elif state != "true":
    print("Starting stopped registry container...")
    pc.ssh(srv, f"docker start {pc.REGISTRY_CONTAINER}")
print("OK: registry container running")

# 7. registry answering
for _ in range(10):
    if pc.registry_running(srv):
        break
    import time
    time.sleep(1)
else:
    sys.exit("Error: registry does not answer on 127.0.0.1:5000 (check `docker logs ubk-registry`).")
print("OK: registry answers on 127.0.0.1:5000")

print(f"\\nInfrastructure ready. Next: python bin/prod-dc-publish.py")
'''


def generate(bin_dir: Path):
    script = bin_dir / "prod-dc-check-infra.py"
    script.write_text(_CONTENT)
    script.chmod(0o755)
