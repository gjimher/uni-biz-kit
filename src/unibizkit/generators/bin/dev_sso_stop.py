from pathlib import Path
from .. import dev_ports


def generate(bin_dir: Path, sso_dir: Path):
    script = bin_dir / 'dev-sso-stop.py'
    script.write_text(_content(sso_dir), encoding='utf-8')
    script.chmod(0o755)


def _content(sso_dir: Path) -> str:
    header = (
        '#!/usr/bin/python3\n'
        '"""Stop SSO containers without removing volumes (use dev-sso-start.py to resume)."""\n'
        '\n'
        f'SSO_DIR = "{sso_dir}"\n'
        f'COMPOSE_PROJECT = "unibizkit-sso-{dev_ports.ENV_NUM:02d}"\n'
    )
    return header + _body()


def _body() -> str:
    return """
import subprocess
import sys
from pathlib import Path

sso_dir = Path(SSO_DIR)
dc_file = sso_dir / 'docker-compose.yml'

if not dc_file.exists():
    print("Nothing to stop (dev-sso/docker-compose.yml not found).")
    sys.exit(0)

COMPOSE = None
for candidate in (['docker', 'compose'], ['docker-compose']):
    if subprocess.run(candidate + ['version'], capture_output=True).returncode == 0:
        COMPOSE = candidate
        break

if COMPOSE is None:
    sys.exit("Error: Docker Compose not found.")

result = subprocess.run(
    COMPOSE + ['-p', COMPOSE_PROJECT, '-f', str(dc_file), 'stop'],
    stdout=sys.stdout, stderr=sys.stderr,
)
sys.exit(result.returncode)
"""
