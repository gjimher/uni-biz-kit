from pathlib import Path
from .. import dev_ports
from ..dev_sso.constants import REALM


def generate(bin_dir: Path):
    script = bin_dir / 'dev-sso-chrome.py'
    script.write_text(_content(), encoding='utf-8')
    script.chmod(0o755)


def _content() -> str:
    header = (
        '#!/usr/bin/python3\n'
        '"""Get a Kerberos ticket and launch Google Chrome for SSO testing."""\n'
        '\n'
        f'REALM = "{REALM}"\n'
        f'KC_PORT = {dev_ports.KC_PORT}\n'
        f'REMOTE_DEBUG_PORT = {dev_ports.CHROME_DEBUG}\n'
        f'COMPOSE_PROJECT = "unibizkit-sso-{dev_ports.ENV_NUM:02d}"\n'
        'REALM_NAME = "dev-local"\n'
    )
    return header + _body()


def _body() -> str:
    # Plain string — no f-string, so {KC_PORT} etc pass through as literals
    # that become variable references in the generated script.
    return """
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sso_dir = root_dir / 'dev-sso'
dc_file = sso_dir / 'docker-compose.yml'
caches_dir = sso_dir / 'caches'
krb5_host_conf = sso_dir / 'krb5-host.conf'
kc_url = f"http://keycloak.dev.local:{KC_PORT}/realms/{REALM_NAME}/account"

_sec_file = root_dir / 'security_extended.json'
if not _sec_file.exists():
    sys.exit(f"Not found: {_sec_file}\\nRun the generator first.")
USERS = json.loads(_sec_file.read_text()).get("users", [])
USER_MAP = {u["email"].split("@")[0]: u for u in USERS}

parser = argparse.ArgumentParser(description="Get Kerberos ticket and launch Google Chrome for SSO.")
parser.add_argument("user", nargs="?", default=list(USER_MAP)[0] if USER_MAP else "admin",
                    help=f"Username (default: first user). Available: {', '.join(USER_MAP)}")
parser.add_argument(
    "--remote-debug",
    action="store_true",
    help=f"Enable Chrome remote debugging on port {REMOTE_DEBUG_PORT}.",
)
args = parser.parse_args()

user = USER_MAP.get(args.user)
if user is None:
    sys.exit(f"Unknown user '{args.user}'. Available: {', '.join(USER_MAP)}")

username = user["email"].split("@")[0]
password = user["password"]
cc_file = caches_dir / f"krb5cc_{username}"

if not dc_file.exists():
    sys.exit("SSO environment not running. Start it first with: python bin/dev-sso-start.py")

COMPOSE = None
for candidate in (['docker', 'compose'], ['docker-compose']):
    if subprocess.run(candidate + ['version'], capture_output=True).returncode == 0:
        COMPOSE = candidate
        break
if COMPOSE is None:
    sys.exit("Error: Docker Compose not found.")

print(f"Getting Kerberos ticket for {username}@{REALM}...")
result = subprocess.run(
    COMPOSE + ['-p', COMPOSE_PROJECT, '-f', str(dc_file), 'exec', '-T', 'kdc', 'bash', '-c',
        f"echo {repr(password)} | "
        f"KRB5CCNAME=FILE:/caches/krb5cc_{username} kinit {username}@{REALM} && "
        f"KRB5CCNAME=FILE:/caches/krb5cc_{username} kvno HTTP/keycloak.dev.local@{REALM} && "
        f"chmod 644 /caches/krb5cc_{username}"
    ],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
)
if result.returncode != 0:
    sys.exit(f"kinit failed:\\n{result.stderr}")

browser = None
for candidate in ('google-chrome', 'google-chrome-stable'):
    if subprocess.run(['which', candidate], capture_output=True).returncode == 0:
        browser = candidate
        break
if browser is None:
    sys.exit(
        "Google Chrome not found. Install it with:\\n"
        "  wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb\\n"
        "  sudo apt install /tmp/chrome.deb"
    )

profile_dir = caches_dir / 'chrome' / f'profile-{username}'
profile_dir.mkdir(parents=True, exist_ok=True)

print(f"Ticket obtained. Launching {browser} as {username}...")

env = os.environ.copy()
env['KRB5CCNAME'] = f'FILE:{cc_file}'
env['KRB5_CONFIG'] = str(krb5_host_conf)

chrome_cmd = [
    browser,
    f'--user-data-dir={profile_dir}',
    '--auth-server-allowlist=keycloak.dev.local',
    '--auth-negotiate-delegate-allowlist=keycloak.dev.local',
]
if args.remote_debug:
    chrome_cmd.append(f'--remote-debugging-port={REMOTE_DEBUG_PORT}')
chrome_cmd.append(kc_url)

subprocess.Popen(
    chrome_cmd,
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
print(f"{browser} launched → {kc_url}")
"""
