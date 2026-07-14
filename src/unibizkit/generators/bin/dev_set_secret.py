from pathlib import Path


_CONTENT = r'''#!/usr/bin/python3
"""Manage custom Edge Function secrets for the local Supabase instance.

Values are stored only in backend/.env.secrets with mode 0600. By default the
value is requested without echo; --stdin supports secret-manager pipelines.
After a change, dev-supabase-start.py synchronizes the secrets into the Edge
Functions environment and restarts Supabase only when its effective input changed.
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
import getpass
import os
import re
import subprocess


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("key", nargs="?")
parser.add_argument("--stdin", action="store_true", help="read the value from stdin")
parser.add_argument("--delete", action="store_true", help="remove KEY")
parser.add_argument("--list", action="store_true", help="list configured names without values")
args = parser.parse_args()
if not args.list and not args.key:
    parser.error("KEY is required unless --list is used")
if args.key and not re.fullmatch(r"[A-Z][A-Z0-9_]*", args.key):
    parser.error("KEY must match [A-Z][A-Z0-9_]*")

root_dir = Path(__file__).parent.parent
secrets_path = root_dir / "backend" / ".env.secrets"
if args.list:
    if secrets_path.exists():
        for line in secrets_path.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                print(line.partition("=")[0])
    raise SystemExit(0)

if args.delete:
    value = None
else:
    value = sys.stdin.read().rstrip("\n") if args.stdin else getpass.getpass("Value: ")
    if not value:
        sys.exit("Error: secret value cannot be empty")
    if "\n" in value or "\r" in value:
        sys.exit("Error: secret value must be a single line")

lines = secrets_path.read_text(encoding="utf-8").splitlines() if secrets_path.exists() else []
lines = [line for line in lines if not line.startswith(f"{args.key}=")]
if value is not None:
    lines.append(f"{args.key}={value}")
secrets_path.parent.mkdir(parents=True, exist_ok=True)
temporary = secrets_path.with_name(secrets_path.name + ".tmp")
temporary.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
os.chmod(temporary, 0o600)
temporary.replace(secrets_path)
os.chmod(secrets_path, 0o600)

result = subprocess.run([sys.executable, str(root_dir / "bin" / "dev-supabase-start.py")])
if result.returncode != 0:
    raise SystemExit(result.returncode)
print(f"Secret {args.key} {'deleted' if args.delete else 'updated'}; local Supabase reconciled.")
'''


def generate(bin_dir: Path):
    path = bin_dir / "dev-set-secret.py"
    path.write_text(_CONTENT, encoding="utf-8")
    path.chmod(0o755)
