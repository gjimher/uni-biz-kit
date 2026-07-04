from pathlib import Path
from .dev_supabase_start import SUPABASE_CLI_VERSION


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-stop.py"
    with open(script, 'w', encoding='utf-8') as f:
        f.write(f"""\
#!/usr/bin/python3
\"\"\"Stop the local Supabase instance.

Idempotent: safe to run when the instance is already stopped or was never
initialized; it just makes sure the containers end up stopped.

Runs `supabase stop` in backend/, which stops the app's containers and backs
up the database data to a Docker volume — data is preserved and comes back on
the next dev-supabase-start.py. To delete the instance and its data use
dev-supabase-remove.py instead.
\"\"\"
import sys
from pathlib import Path

SUPABASE_CLI_VERSION = "{SUPABASE_CLI_VERSION}"

if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\\n"
        f"  python bin/{{Path(__file__).name}}\\n"
        f"(not python3 or direct execution)"
    )

import argparse
import os
import subprocess

argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
).parse_args()

backend_dir = Path(__file__).parent.parent / 'backend'
supabase_dir = backend_dir / 'supabase'

if not supabase_dir.exists():
    print("Supabase not initialized — nothing to stop.")
    sys.exit(0)

os.chdir(backend_dir)

result = subprocess.run(
    ['npx', f'supabase@{{SUPABASE_CLI_VERSION}}', 'stop'],
    stdout=sys.stdout, stderr=sys.stderr,
)
if result.returncode != 0:
    sys.exit(f"supabase stop failed with code {{result.returncode}}")

print("Supabase stopped.")
""")
    script.chmod(0o755)
