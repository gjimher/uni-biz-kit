from pathlib import Path

SUPABASE_CLI_VERSION = "2.88.1"

_SCRIPT_HEAD = f'''\
#!/usr/bin/python3
"""Create and start Supabase for local development."""
import sys
from pathlib import Path

SUPABASE_CLI_VERSION = "{SUPABASE_CLI_VERSION}"
'''

_SCRIPT_BODY = r'''
if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\n"
        f"  python bin/{Path(__file__).name}\n"
        f"(not python3 or direct execution)"
    )

import json
import os
import re
import subprocess
import tomllib

root_dir = Path(__file__).parent.parent
backend_dir = root_dir / 'backend'
frontend_dir = root_dir / 'frontend'
supabase_dir = backend_dir / 'supabase'
config_toml = supabase_dir / 'config.toml'
delta_toml = backend_dir / 'supabase_config_dev.toml'
sso_delta_toml = backend_dir / 'supabase_sso_config_dev.toml'

os.chdir(backend_dir)


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


def _delta_is_applied(config_path, delta_path):
    """Return True if all values from delta_path are already present in config_path."""
    with open(config_path, 'rb') as f:
        config_data = tomllib.load(f)
    with open(delta_path, 'rb') as f:
        delta_data = tomllib.load(f)
    return _dict_contains(config_data, delta_data)


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


delta_files = [delta_toml] + ([sso_delta_toml] if sso_delta_toml.exists() else [])

if supabase_dir.exists():
    if not all(_delta_is_applied(config_toml, d) for d in delta_files):
        print("Config has changes — stopping Supabase, applying config, restarting...")
        result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'stop'],
                                stdout=sys.stdout, stderr=sys.stderr)
        if result.returncode != 0:
            sys.exit(f"supabase stop failed with code {result.returncode}")
        for d in delta_files:
            _apply_delta(config_toml, d)
        result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'start'],
                                stdout=sys.stdout, stderr=sys.stderr)
        if result.returncode != 0:
            sys.exit(f"supabase start failed with code {result.returncode}")
        print("Supabase restarted with updated config.")
    else:
        print("Config is up to date. Nothing to do.")
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
result = subprocess.run(['npx', f'supabase@{SUPABASE_CLI_VERSION}', 'start'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"supabase start failed with code {result.returncode}")

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
api_url = status['API_URL']
anon_key = status['ANON_KEY']
db_url = status['DB_URL']
service_role_key = status['SERVICE_ROLE_KEY']

print("Writing .env files...")
(backend_dir / '.env').write_text(
    f"DB_URL={db_url}\nSUPABASE_URL={api_url}\nSUPABASE_SERVICE_ROLE_KEY={service_role_key}\n"
)
_upsert_env(frontend_dir / '.env.development', {
    'VITE_SUPABASE_URL': api_url,
    'VITE_SUPABASE_KEY': anon_key,
})

print("Supabase is ready.")
'''


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-start.py"
    script.write_text(_SCRIPT_HEAD + _SCRIPT_BODY)
    script.chmod(0o755)
