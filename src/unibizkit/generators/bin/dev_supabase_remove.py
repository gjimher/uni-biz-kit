from pathlib import Path
from .dev_supabase_start import SUPABASE_CLI_VERSION


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-remove.py"
    with open(script, 'w', encoding='utf-8') as f:
        f.write(f"""\
#!/usr/bin/python3
\"\"\"Stop and remove the local Supabase instance (no backup).

Idempotent: exits successfully when there is nothing to remove.

* Asks for confirmation unless -f/--force is given.
* Runs `supabase stop --no-backup`: removes the app's containers and data
  volumes. All database data is lost.
* Deletes generated Supabase state such as config.toml and migrations, but
  preserves backend/supabase/functions because those files come from the model.

For a stop that preserves data use dev-supabase-stop.py.
\"\"\"
import sys
from pathlib import Path

SUPABASE_CLI_VERSION = "{SUPABASE_CLI_VERSION}"

if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\\n"
        f"  python bin/{Path(__file__).name}\\n"
        f"(not python3 or direct execution)"
    )

import argparse
import os
import shutil
import subprocess

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument('-f', '--force', action='store_true', help="Skip confirmation prompt")
args = parser.parse_args()

backend_dir = Path(__file__).parent.parent / 'backend'
supabase_dir = backend_dir / 'supabase'

if not supabase_dir.exists() or not any(path.name != 'functions' for path in supabase_dir.iterdir()):
    print("Nothing to remove (only generated Edge Functions may remain).")
    sys.exit(0)

if not args.force:
    answer = input("This will stop Supabase and delete its local config, migrations and data. Are you sure? [y/N] ")
    if answer.strip().lower() != 'y':
        print("Aborted.")
        sys.exit(0)

os.chdir(backend_dir)

result = subprocess.run(['npx', f'supabase@{{SUPABASE_CLI_VERSION}}', 'stop', '--no-backup'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(result.returncode)

print("Removing generated backend/supabase state (preserving functions)...")
for path in supabase_dir.iterdir():
    if path.name == 'functions':
        continue
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
print("Done.")
""")
    script.chmod(0o755)
