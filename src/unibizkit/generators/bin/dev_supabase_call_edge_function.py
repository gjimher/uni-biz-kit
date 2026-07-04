from pathlib import Path


_SCRIPT = r'''#!/usr/bin/python3
"""Log in as a seeded user and call a local Supabase Edge Function.

* Reads SUPABASE_URL and the anon key from backend/.env (direct Kong URL, so
  no dev server is needed).
* If PASSWORD is omitted, it is looked up in security_extended.json.
* Logs in with email + password to obtain a user JWT, then POSTs JSON_ARGS to
  /functions/v1/EDGE_FUNCTION with it — the call runs with the user's real
  permissions, exactly like a call made from the app.
* Prints {"status": ..., "body": ...} as JSON; exits non-zero on HTTP >= 400.
"""
import sys
from pathlib import Path

if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\n"
        f"  python bin/{Path(__file__).name}\n"
        f"(not python3 or direct execution)"
    )

import json
import os
import urllib.error
import urllib.request


def usage():
    sys.exit(
        __doc__ + "\n"
        "Usage:\n"
        f"  python bin/{Path(__file__).name} USER [PASSWORD] EDGE_FUNCTION [JSON_ARGS]\n\n"
        "Examples:\n"
        f"  python bin/{Path(__file__).name} user1@test.com order-shipping-costs '{{\"id\": 1}}'\n"
        f"  python bin/{Path(__file__).name} user1@test.com workflow-transition '{{\"concept\":\"order\",\"id\":1,\"to_state\":\"initial\",\"comment\":\"Back to initial\"}}'\n"
        f"  python bin/{Path(__file__).name} user1@test.com useruser order-shipping-costs '{{\"id\": 1}}'"
    )


def parse_args(argv):
    if len(argv) not in (2, 3, 4):
        usage()
    user = argv[0]
    password = None
    function_name = None
    payload = {}

    if len(argv) == 2:
        function_name = argv[1]
    elif len(argv) == 3:
        if argv[2].lstrip().startswith(("{", "[")):
            function_name = argv[1]
            payload = parse_json_arg(argv[2])
        else:
            password = argv[1]
            function_name = argv[2]
    else:
        password = argv[1]
        function_name = argv[2]
        payload = parse_json_arg(argv[3])

    return user, password, function_name, payload


def parse_json_arg(raw):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON_ARGS: {exc}")
    if not isinstance(value, (dict, list)):
        sys.exit("JSON_ARGS must be a JSON object or array.")
    return value


def load_env(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def find_seed_password(root_dir, email):
    security_path = root_dir / "security_extended.json"
    if not security_path.exists():
        sys.exit(
            f"Password was not provided and {security_path} does not exist. "
            "Regenerate the app or pass PASSWORD explicitly."
        )
    security = json.loads(security_path.read_text())
    for user in security.get("users", []):
        if user.get("email") == email:
            password = user.get("password")
            if not password:
                sys.exit(f"User {email} has no password in {security_path}.")
            return password
    sys.exit(f"Password was not provided and user {email} was not found in {security_path}.")


def request_json(method, url, headers, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw
        return exc.code, body


def main():
    user, password, function_name, payload = parse_args(sys.argv[1:])
    root_dir = Path(__file__).parent.parent
    # Reach Supabase (Kong) directly via backend/.env, not the Vite proxy.
    backend_env = load_env(root_dir / "backend" / ".env")
    api_url = backend_env.get("SUPABASE_URL")
    anon_key = backend_env.get("SUPABASE_ANON_KEY")
    if not api_url or not anon_key:
        sys.exit("SUPABASE_URL / SUPABASE_ANON_KEY not found in backend/.env")

    if password is None:
        password = find_seed_password(root_dir, user)

    login_status, login_body = request_json(
        "POST",
        f"{api_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        body={"email": user, "password": password},
    )
    if login_status != 200:
        print(json.dumps({"status": login_status, "body": login_body}, indent=2, sort_keys=True))
        sys.exit(1)

    access_token = login_body["access_token"]
    status, body = request_json(
        "POST",
        f"{api_url}/functions/v1/{function_name}",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        body=payload,
    )
    print(json.dumps({"status": status, "body": body}, indent=2, sort_keys=True))
    if status >= 400:
        sys.exit(1)


if __name__ == "__main__":
    main()
'''


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-call-edge-function.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    script.chmod(0o755)
