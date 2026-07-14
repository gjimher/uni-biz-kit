from pathlib import Path


_CONTENT = r'''#!/usr/bin/python3
"""Manage custom Edge Function secrets on the production server.

Values are stored only in ~/ubk/<app>/.env.secrets with mode 0600. By default
the value is requested without echo; --stdin supports secret-manager pipelines.
The functions container is recreated so Deno receives the updated environment.
"""
import argparse
import base64
import getpass
import re
import sys

import prod_dc_common as pc

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

srv = pc.deployment_config()["prod_dcd_ssh_srv"]
path = f"$HOME/{pc.REMOTE_APP_DIR}/.env.secrets"
if args.list:
    result = pc.ssh(srv, f"test -f {path} && sed -n 's/=.*//p' {path} || true", capture=True)
    print(result.stdout, end="")
    raise SystemExit(0)

if args.delete:
    value64 = ""
else:
    value = sys.stdin.read().rstrip("\n") if args.stdin else getpass.getpass("Value: ")
    if not value:
        sys.exit("Error: secret value cannot be empty")
    value64 = base64.b64encode(value.encode()).decode()

script = r"""set -eu
mkdir -p "$HOME/__REMOTE__"
file="$HOME/__REMOTE__/.env.secrets"
touch "$file"
chmod 600 "$file"
tmp="${file}.tmp"
grep -v '^__KEY__=' "$file" > "$tmp" || true
if [ -n '__VALUE64__' ]; then
  printf '__KEY__=' >> "$tmp"
  printf '%s' '__VALUE64__' | base64 -d >> "$tmp"
  printf '\n' >> "$tmp"
fi
mv "$tmp" "$file"
chmod 600 "$file"
""".replace("__REMOTE__", pc.REMOTE_APP_DIR).replace("__KEY__", args.key).replace("__VALUE64__", value64)
pc.ssh(srv, "bash -s", input=script)
compose = pc.compose_cmd(srv)
pc.ssh(srv, f"cd $HOME/{pc.REMOTE_APP_DIR} && {compose} up -d --force-recreate --no-deps functions")
print(f"Secret {args.key} {'deleted' if args.delete else 'updated'}; functions recreated.")
'''


def generate(bin_dir: Path):
    path = bin_dir / "prod-dc-set-secret.py"
    path.write_text(_CONTENT, encoding="utf-8")
    path.chmod(0o755)
