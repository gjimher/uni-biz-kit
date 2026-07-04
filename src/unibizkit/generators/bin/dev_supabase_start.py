from pathlib import Path
from .. import dev_ports

SUPABASE_CLI_VERSION = "2.88.1"

_SCRIPT_BODY = r'''
if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\n"
        f"  python bin/{Path(__file__).name}\n"
        f"(not python3 or direct execution)"
    )

import argparse
import json
import hashlib
import os
import re
import socket
import socketserver
import subprocess
import threading
import tomllib
import http.server
import urllib.error
import urllib.request

argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
).parse_args()

root_dir = Path(__file__).parent.parent
backend_dir = root_dir / 'backend'
frontend_dir = root_dir / 'frontend'
supabase_dir = backend_dir / 'supabase'
config_toml = supabase_dir / 'config.toml'
delta_toml = backend_dir / 'supabase_config_dev.toml'
sso_delta_toml = backend_dir / 'supabase_sso_config_dev.toml'

os.chdir(backend_dir)


# --- Temporary /api -> Kong proxy for a cold `supabase start` ----------------
# `supabase start` verifies storage through [api].external_url, which is set to the
# Vite dev proxy (http://localhost:_FRONTEND_PORT/<base>/api) so auth email links
# and storage URLs stay same-origin with the SPA. When no dev server is running
# that URL is unreachable and the CLI rolls back the otherwise-healthy stack with a
# "connection refused" on .../storage/v1/bucket. To make a cold start self-sufficient
# we bring up a tiny stdlib proxy on the frontend port for the duration of `start`
# only, forwarding <base>/api/* to Kong (stripping the prefix, exactly like Vite).
# If a real dev server is already listening we leave it alone.
def _port_in_use(port):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(('127.0.0.1', port)) == 0


class _ApiProxyHandler(http.server.BaseHTTPRequestHandler):
    def _forward(self):
        if not self.path.startswith(_API_PROXY_PREFIX):
            self.send_error(404)
            return
        target = f'http://127.0.0.1:{_SUPABASE_API_PORT}{self.path[len(_API_PROXY_PREFIX):] or "/"}'
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(target, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() not in ('host', 'content-length'):
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self._relay(resp.status, resp.getheaders(), resp.read())
        except urllib.error.HTTPError as exc:
            self._relay(exc.code, exc.headers.items(), exc.read())
        except Exception:
            self.send_error(502)

    def _relay(self, status, headers, payload):
        self.send_response(status)
        for key, value in headers:
            if key.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                self.send_header(key, value)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def __getattr__(self, name):
        # Forward every HTTP method (GET/HEAD/POST/...) through the same handler.
        if name.startswith('do_'):
            return self._forward
        raise AttributeError(name)

    def log_message(self, *args):
        pass


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _supabase_start():
    """Run `supabase start`, fronting it with the temporary /api proxy if needed."""
    httpd = None
    if not _port_in_use(_FRONTEND_PORT):
        httpd = _ProxyServer(('127.0.0.1', _FRONTEND_PORT), _ApiProxyHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        return subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'start'],
                              stdout=sys.stdout, stderr=sys.stderr)
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()


def _parse_toml_sections(text):
    """Split TOML text into list of (header_name, block_text) pairs.
    Root-level content has header ''. Each block includes its [header] line."""
    lines = text.splitlines(keepends=True)
    sections = []
    current_header = ''
    current_start = 0
    for i, line in enumerate(lines):
        m = re.match(r'^\s*\[([^\[\]]+)\]\s*(?:#.*)?$', line)
        if m and i > 0:
            sections.append((current_header, ''.join(lines[current_start:i])))
            current_header = m.group(1)
            current_start = i
    sections.append((current_header, ''.join(lines[current_start:])))
    return sections


def _merge_keys_into_block(base_text, delta_text):
    """For each key=value in delta_text, replace or append that key in base_text."""
    base_lines = base_text.splitlines(keepends=True)
    for delta_line in delta_text.splitlines(keepends=True):
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*', delta_line)
        if not m:
            continue
        key = m.group(1)
        replaced = False
        for i, line in enumerate(base_lines):
            if re.match(r'^\s*' + re.escape(key) + r'\s*=', line):
                base_lines[i] = delta_line
                replaced = True
                break
        if not replaced:
            base_lines.append(delta_line)
    return ''.join(base_lines)


def _apply_delta(config_path, delta_path):
    """Merge delta TOML onto config TOML and write the result back to config_path."""
    config_text = config_path.read_text()
    delta_text = delta_path.read_text()
    config_sections = _parse_toml_sections(config_text)
    delta_sections = _parse_toml_sections(delta_text)
    config_dict = {h: text for h, text in config_sections}
    config_order = [h for h, _ in config_sections]
    new_headers = []
    for delta_header, delta_block in delta_sections:
        if delta_header in config_dict:
            config_dict[delta_header] = _merge_keys_into_block(config_dict[delta_header], delta_block)
        else:
            config_dict[delta_header] = delta_block
            new_headers.append(delta_header)
    config_path.write_text(''.join([config_dict[h] for h in config_order + new_headers]))


def _dict_contains(config, delta):
    for k, v in delta.items():
        if k not in config:
            return False
        if isinstance(v, dict):
            if not isinstance(config[k], dict) or not _dict_contains(config[k], v):
                return False
        elif config[k] != v:
            return False
    return True


def _deep_merge(base, override):
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _merged_deltas_applied(config_path, delta_paths):
    """Return True if the merged result of all deltas (later overrides earlier) is in config."""
    with open(config_path, 'rb') as f:
        config_data = tomllib.load(f)
    merged = {}
    for delta_path in delta_paths:
        with open(delta_path, 'rb') as f:
            merged = _deep_merge(merged, tomllib.load(f))
    return _dict_contains(config_data, merged)


def _upsert_env(path, values):
    existing = {}
    order = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                existing[key] = value.strip()
                order.append(key)
    for key, value in values.items():
        if key not in existing:
            order.append(key)
        existing[key] = value
    path.write_text(''.join(f"{key}={existing[key]}\n" for key in dict.fromkeys(order)))


def _functions_signature(functions_dir):
    digest = hashlib.sha256()
    if not functions_dir.exists():
        return ''
    for path in sorted(functions_dir.rglob('*')):
        if not path.is_file():
            continue
        digest.update(str(path.relative_to(functions_dir)).encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def _stored_functions_signature(marker_path):
    if not marker_path.exists():
        return None
    return marker_path.read_text().strip()


def _project_id(config_path):
    with open(config_path, 'rb') as f:
        return tomllib.load(f).get('project_id')


def _edge_runtime_running(config_path):
    project_id = _project_id(config_path)
    if not project_id:
        return False
    result = subprocess.run(
        [
            'docker',
            'inspect',
            '-f',
            '{{.State.Running}}',
            f'supabase_edge_runtime_{project_id}',
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == 'true'


def _restart_supabase(reason):
    print(f"{reason} — restarting Supabase...")
    result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'stop'],
                            stdout=sys.stdout, stderr=sys.stderr)
    if result.returncode != 0:
        sys.exit(f"supabase stop failed with code {result.returncode}")
    result = _supabase_start()
    if result.returncode != 0:
        sys.exit(f"supabase start failed with code {result.returncode}")


delta_files = [delta_toml] + ([sso_delta_toml] if sso_delta_toml.exists() else [])
functions_signature_path = supabase_dir / '.functions_signature'
current_functions_signature = _functions_signature(supabase_dir / 'functions')
functions_changed = current_functions_signature != _stored_functions_signature(functions_signature_path)

if config_toml.exists():
    config_changed = not _merged_deltas_applied(config_toml, delta_files)
    if config_changed or functions_changed:
        print("Config or Edge Functions changed.")
        result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'stop'],
                                stdout=sys.stdout, stderr=sys.stderr)
        if result.returncode != 0:
            sys.exit(f"supabase stop failed with code {result.returncode}")
        if config_changed:
            for d in delta_files:
                _apply_delta(config_toml, d)
        result = _supabase_start()
        if result.returncode != 0:
            sys.exit(f"supabase start failed with code {result.returncode}")
        functions_signature_path.write_text(current_functions_signature)
        print("Supabase restarted with updated config or Edge Functions.")
    else:
        status_check = subprocess.run(
            ['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'status', '-o', 'json'],
            capture_output=True, text=True,
        )
        if status_check.returncode != 0:
            print("Config is up to date but Supabase is not running — starting...")
            result = _supabase_start()
            if result.returncode != 0:
                sys.exit(f"supabase start failed with code {result.returncode}")
            functions_signature_path.write_text(current_functions_signature)
            print("Supabase started.")
        elif not _edge_runtime_running(config_toml):
            _restart_supabase("Supabase status is up but Edge Runtime is not running")
            functions_signature_path.write_text(current_functions_signature)
            print("Supabase restarted.")
        else:
            print("Config is up to date and Supabase is running. Nothing to do.")
    sys.exit(0)

print("Initializing Supabase...")
result = subprocess.run(['npx', '-y', f'supabase@{SUPABASE_CLI_VERSION}', 'init'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"supabase init failed with code {result.returncode}")

print("Applying config deltas to supabase/config.toml...")
for d in delta_files:
    _apply_delta(config_toml, d)

print("Starting Supabase...")
result = _supabase_start()
if result.returncode != 0:
    sys.exit(f"supabase start failed with code {result.returncode}")
functions_signature_path.write_text(current_functions_signature)

print("Creating initial migration...")
result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'migration', 'new', 'init_schema'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"supabase migration new failed with code {result.returncode}")

print("Getting Supabase status...")
result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'status', '-o', 'json'],
                        capture_output=True, text=True)
if result.returncode != 0:
    sys.exit(f"supabase status failed: {result.stderr}")
status = json.loads(result.stdout)
anon_key = status['ANON_KEY']
db_url = status['DB_URL']
service_role_key = status['SERVICE_ROLE_KEY']

# backend/.env is read by tooling/tests/reset, which reach the API without a running
# dev server, so point them straight at Kong (status['API_URL'] is [api].external_url,
# i.e. the Vite proxy, which would need the dev server up). The app's frontend .env
# (VITE_SUPABASE_URL = the proxy) is written by the frontend generator; here we only
# add the anon key it needs.
supabase_url = f"http://localhost:{_SUPABASE_API_PORT}"

print("Writing .env files...")
(backend_dir / '.env').write_text(
    f"DB_URL={db_url}\nSUPABASE_URL={supabase_url}\n"
    f"SUPABASE_ANON_KEY={anon_key}\nSUPABASE_SERVICE_ROLE_KEY={service_role_key}\n"
)
_upsert_env(frontend_dir / '.env.development', {
    'VITE_SUPABASE_KEY': anon_key,
})

print("Supabase is ready.")
'''


def generate(bin_dir: Path, base_uri: str = "/"):
    # base_uri always ends with / (normalized by SchemaProcessor); the cold-start
    # proxy strips "<base>/api" before forwarding to Kong, matching vite.config.js.
    base_prefix = base_uri.rstrip("/")
    head = f'''\
#!/usr/bin/python3
"""Create and start the app's local Supabase instance.

Idempotent: run it as many times as needed; it converges the instance to a
running, up-to-date state. What it does depends on the current state:

* First run: initializes backend/supabase (supabase init), applies the dev
  config deltas (supabase_config_dev.toml and, when SSO is enabled,
  supabase_sso_config_dev.toml) onto supabase/config.toml, starts the stack,
  creates the initial migration, and writes the connection credentials:
  - backend/.env: DB_URL, SUPABASE_URL (direct Kong URL) and the anon /
    service-role keys, used by the test suite and the other dev scripts.
  - frontend/.env.development: adds VITE_SUPABASE_KEY (anon key).
* Later runs: if the config deltas or the Edge Functions changed, restarts
  the stack to apply them; if the stack is stopped, starts it; if the Edge
  Runtime container died, restarts the stack; otherwise does nothing.

During a cold `supabase start` (no dev server running) it serves a temporary
/api -> Kong proxy on the frontend port, so the Supabase CLI can verify
storage through [api].external_url, which points at the Vite dev proxy.

The database is not touched: load schema and data with
dev-supabase-reset-schema-and-data.py.
"""
import sys
from pathlib import Path

SUPABASE_CLI_VERSION = "{SUPABASE_CLI_VERSION}"
_FRONTEND_PORT = {dev_ports.FRONTEND}
_SUPABASE_API_PORT = {dev_ports.SUPABASE_API}
_API_PROXY_PREFIX = "{base_prefix}/api"
'''
    script = bin_dir / "dev-supabase-start.py"
    script.write_text(head + _SCRIPT_BODY)
    script.chmod(0o755)
