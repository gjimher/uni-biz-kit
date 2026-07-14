from pathlib import Path


def generate(bin_dir: Path):
    script = bin_dir / "dev-deploy-data.py"
    script.write_text(r'''#!/usr/bin/python3
"""Apply deployed data to the local database.

Usage:
  python bin/dev-deploy-data.py
  python bin/dev-deploy-data.py PATH/TO/deployed_data.jsonc

Without a path, applies the generated deployed_data_extended.json. The whole
operation is transactional and reports inserted, updated and removed rows.
"""
import sys
from pathlib import Path

if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\n"
        f"  python bin/{Path(__file__).name}\n"
        f"(not python3 or direct execution)"
    )

import argparse
import json
import psycopg2

root_dir = Path(__file__).parent.parent
backend_dir = root_dir / "backend"
sys.path.insert(0, str(backend_dir))
from deployed_data_runtime import apply_deployed_data


def load_env(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("file", nargs="?", type=Path, default=root_dir / "deployed_data_extended.json")
args = parser.parse_args()
data_path = args.file.resolve()
if not data_path.exists():
    sys.exit(f"Deployed data file does not exist: {data_path}")
db_url = load_env(backend_dir / ".env").get("DB_URL")
if not db_url:
    sys.exit("DB_URL not found in backend/.env")

conn = psycopg2.connect(db_url)
try:
    stats = apply_deployed_data(conn, root_dir / "concepts_extended.json", data_path)
finally:
    conn.close()
print(json.dumps(stats, indent=2, sort_keys=True))
''', encoding="utf-8")
    script.chmod(0o755)
