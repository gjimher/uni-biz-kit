from pathlib import Path

_CONTENT = '''\
"""Shared helpers for the bin/prod-* scripts. Not a script itself.

Everything is driven by deployment_extended.json in the app root, including
the SSH server, base port and prod_versioning policy. The remote layout is:

  ~/ubk/<app>/.env                          secrets + PUBLIC_HOST (created once)
  ~/ubk/<app>/docker-compose-<version>.yml  one immutable file per version
  ~/ubk/<app>/docker-compose.yml            symlink to the active version
  ~/ubk/<app>/releases/<version>.sha256     content hash guarding immutability

Images live in a docker registry container (ubk-registry) bound to the remote
loopback:5000, under the <app>/ namespace.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_ID = ROOT_DIR.name
REMOTE_APP_DIR = f"ubk/{APP_ID}"  # relative to the remote $HOME
REMOTE_REGISTRY = "localhost:5000"
REGISTRY_CONTAINER = "ubk-registry"


def deployment_config():
    path = ROOT_DIR / "deployment_extended.json"
    if not path.exists():
        sys.exit(f"Error: {path} not found. Generate the app first (run pytest or uni-biz-kit).")
    return json.loads(path.read_text())


def run(cmd, check=True, capture=False, cwd=None, env=None, input=None):
    result = subprocess.run(
        cmd, cwd=cwd, env=env, input=input, text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        sys.exit(f"Error: command failed ({result.returncode}): {' '.join(map(str, cmd))}")
    return result


def ssh(srv, command, check=True, capture=False, input=None):
    return run(["ssh", "-o", "BatchMode=yes", srv, command],
               check=check, capture=capture, input=input)


def ssh_output(srv, command, check=True):
    return ssh(srv, command, check=check, capture=True).stdout.strip()


def remote_python(srv, script, check=True, capture=False):
    """Run a python3 script on the remote host (piped through stdin)."""
    return ssh(srv, "python3 -", check=check, capture=capture, input=script)


def remote_host(srv):
    """Resolve the actual hostname/IP behind an ssh alias (for public URLs)."""
    out = run(["ssh", "-G", srv], capture=True).stdout
    for line in out.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip()
    sys.exit(f"Error: could not resolve hostname for ssh host {srv!r}")


def compose_cmd(srv):
    """Return the compose command available on the remote ('docker compose' or 'docker-compose')."""
    if ssh(srv, "docker compose version >/dev/null 2>&1", check=False).returncode == 0:
        return "docker compose"
    if ssh(srv, "docker-compose --version >/dev/null 2>&1", check=False).returncode == 0:
        return "docker-compose"
    sys.exit(f"Error: neither 'docker compose' nor 'docker-compose' available on {srv}. "
             "Run bin/prod-dc-check-infra.py for diagnostics.")


# --- Secrets ------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_jwt(payload: dict, secret: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def generate_secrets(public_host: str) -> dict:
    now = int(time.time())
    exp = now + 10 * 365 * 24 * 3600
    jwt_secret = secrets.token_hex(32)

    def api_key(role):
        return sign_jwt({"role": role, "iss": "supabase", "iat": now, "exp": exp}, jwt_secret)

    # Keep dashes so container names read naturally (test-app_db_1, b2c-app_kong_1...).
    project = re.sub(r"[^a-z0-9_-]", "", APP_ID.lower()).strip("-_") or "app"
    return {
        "COMPOSE_PROJECT_NAME": project,
        "PUBLIC_HOST": public_host,
        "POSTGRES_PASSWORD": secrets.token_hex(16),
        "JWT_SECRET": jwt_secret,
        "ANON_KEY": api_key("anon"),
        "SERVICE_ROLE_KEY": api_key("service_role"),
    }


def parse_env(text: str) -> dict:
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def fetch_or_create_secrets(srv) -> dict:
    """Return the remote ~/ubk/<app>/.env as a dict, creating it on first use.

    The .env is the durable source of truth for the app's secrets: it survives
    version publishes and is only removed by prod-dc-remove.py.
    """
    result = ssh(srv, f"cat $HOME/{REMOTE_APP_DIR}/.env", check=False, capture=True)
    if result.returncode == 0 and result.stdout.strip():
        return parse_env(result.stdout)
    env = generate_secrets(remote_host(srv))
    content = "".join(f"{key}={value}\\n" for key, value in env.items())
    ssh(srv,
        f"mkdir -p $HOME/{REMOTE_APP_DIR} && umask 077 && cat > $HOME/{REMOTE_APP_DIR}/.env",
        input=content)
    print(f"Created secrets file {srv}:~/{REMOTE_APP_DIR}/.env")
    return env


# --- Release hashing (version immutability) ------------------------------------
def _hash_tree(digest, base: Path):
    for path in sorted(base.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(base)).encode())
            digest.update(b"\\0")
            digest.update(path.read_bytes())
            digest.update(b"\\0")


def release_hash(compose_content: str, tree_paths, file_paths=()) -> str:
    """Content hash of everything that defines a release: the rendered compose
    file plus every build input of the images.

    tree_paths are hashed recursively (whole directory trees); file_paths are
    hashed individually and skipped when absent. The caller passes the set that
    matches its stack (app vs proxy). Note: prod/docker itself is never hashed
    as a whole because it accumulates the rendered docker-compose-<version>.yml
    files of previous publishes.
    """
    digest = hashlib.sha256()
    digest.update(compose_content.encode())
    for rel in tree_paths:
        _hash_tree(digest, ROOT_DIR / rel)
    for rel in file_paths:
        path = ROOT_DIR / rel
        if path.exists():
            digest.update(rel.encode())
            digest.update(b"\\0")
            digest.update(path.read_bytes())
            digest.update(b"\\0")
    return digest.hexdigest()


def registry_running(srv) -> bool:
    script = (
        "import urllib.request\\n"
        "try:\\n"
        "    urllib.request.urlopen('http://127.0.0.1:5000/v2/', timeout=5)\\n"
        "    print('OK')\\n"
        "except Exception as e:\\n"
        "    print(f'FAIL: {e}')\\n"
    )
    result = remote_python(srv, script, capture=True)
    return result.stdout.strip() == "OK"
'''


def generate(bin_dir: Path):
    (bin_dir / "prod_dc_common.py").write_text(_CONTENT)
