from pathlib import Path
from .. import dev_ports


def generate(bin_dir: Path, sso_dir: Path):
    script = bin_dir / 'dev-sso-remove.py'
    script.write_text(_content(sso_dir), encoding='utf-8')
    script.chmod(0o755)


def _content(sso_dir: Path) -> str:
    header = (
        '#!/usr/bin/python3\n'
        '"""Stop and remove the SSO dev environment (containers + volumes). No backup."""\n'
        '\n'
        f'SSO_DIR = "{sso_dir}"\n'
        f'COMPOSE_PROJECT = "unibizkit-sso-{dev_ports.ENV_NUM:02d}"\n'
    )
    return header + _body()


def _body() -> str:
    return """
import argparse
import subprocess
import sys
from pathlib import Path

sso_dir = Path(SSO_DIR)
dc_file = sso_dir / 'docker-compose.yml'

if not dc_file.exists():
    print("Nothing to remove (dev-sso/docker-compose.yml not found).")
    sys.exit(0)

parser = argparse.ArgumentParser(description="Stop and remove the SSO dev environment.")
parser.add_argument('-f', '--force', action='store_true', help="Skip confirmation prompt")
args = parser.parse_args()

if not args.force:
    answer = input("This will stop containers and delete all SSO volumes (Kerberos DB, Keycloak DB). Are you sure? [y/N] ")
    if answer.strip().lower() != 'y':
        print("Aborted.")
        sys.exit(0)

COMPOSE = None
for candidate in (['docker', 'compose'], ['docker-compose']):
    if subprocess.run(candidate + ['version'], capture_output=True).returncode == 0:
        COMPOSE = candidate
        break

if COMPOSE is None:
    sys.exit("Error: Docker Compose not found.")

result = subprocess.run(
    COMPOSE + ['-p', COMPOSE_PROJECT, '-f', str(dc_file), 'down', '-v'],
    stdout=sys.stdout, stderr=sys.stderr,
)
if result.returncode != 0:
    sys.exit(result.returncode)

print("SSO environment removed.")
"""
