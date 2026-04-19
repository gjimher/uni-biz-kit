from pathlib import Path


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-remove.py"
    with open(script, 'w', encoding='utf-8') as f:
        f.write("""\
#!/usr/bin/python3
\"\"\"Stop and remove the local Supabase instance (no backup).\"\"\"
import sys
from pathlib import Path
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

parser = argparse.ArgumentParser(description="Stop and remove local Supabase instance.")
parser.add_argument('-f', '--force', action='store_true', help="Skip confirmation prompt")
args = parser.parse_args()

backend_dir = Path(__file__).parent.parent / 'backend'
supabase_dir = backend_dir / 'supabase'

if not supabase_dir.exists():
    print("Nothing to remove (backend/supabase does not exist).")
    sys.exit(0)

if not args.force:
    answer = input("This will stop Supabase and delete backend/supabase. Are you sure? [y/N] ")
    if answer.strip().lower() != 'y':
        print("Aborted.")
        sys.exit(0)

os.chdir(backend_dir)

result = subprocess.run(['npx', 'supabase', 'stop', '--no-backup'],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(result.returncode)

print("Removing backend/supabase...")
shutil.rmtree(supabase_dir)
print("Done.")
""")
    script.chmod(0o755)
