from pathlib import Path


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-create.py"
    with open(script, 'w', encoding='utf-8') as f:
        f.write("""\
#!/usr/bin/python3
\"\"\"Create and start Supabase for local development.\"\"\"
import sys
from pathlib import Path
if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\\n"
        f"  python bin/{Path(__file__).name}\\n"
        f"(not python3 or direct execution)"
    )

import json
import os
import shutil
import subprocess

root_dir = Path(__file__).parent.parent
backend_dir = root_dir / 'backend'
frontend_dir = root_dir / 'frontend'
supabase_dir = backend_dir / 'supabase'

os.chdir(backend_dir)

if supabase_dir.exists():
    print("Supabase already created (backend/supabase exists). Nothing to do.")
    sys.exit(0)

print("Initializing Supabase...")
result = subprocess.run(['npx', '-y', 'supabase', 'init'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"supabase init failed with code {result.returncode}")

print("Copying supabase_config_dev.toml -> supabase/config.toml")
shutil.copy(backend_dir / 'supabase_config_dev.toml', supabase_dir / 'config.toml')

print("Starting Supabase...")
result = subprocess.run(['npx', 'supabase', 'start'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"supabase start failed with code {result.returncode}")

print("Creating initial migration...")
result = subprocess.run(['npx', 'supabase', 'migration', 'new', 'init_schema'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"supabase migration new failed with code {result.returncode}")

print("Getting Supabase status...")
result = subprocess.run(['npx', 'supabase', 'status', '-o', 'json'],
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
    f"DB_URL={db_url}\\nSUPABASE_URL={api_url}\\nSUPABASE_SERVICE_ROLE_KEY={service_role_key}\\n"
)
(frontend_dir / '.env').write_text(
    f"REACT_APP_SUPABASE_URL={api_url}\\nREACT_APP_SUPABASE_KEY={anon_key}\\n"
)

print("Supabase is ready.")
""")
    script.chmod(0o755)
