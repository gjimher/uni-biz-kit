"""Fast authenticated calls to local Edge Functions for integration tests."""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import dotenv_values


_auth_cache = {}


def _request_json(method, url, headers, body):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return error.code, parsed


def _auth(email):
    cached = _auth_cache.get(email)
    if cached:
        return cached

    env = dotenv_values("test-app/backend/.env")
    security = json.loads(Path("test-app/security_extended.json").read_text())
    password = next(
        user["password"] for user in security["users"]
        if user["email"] == email
    )
    status, body = _request_json(
        "POST",
        f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        {"apikey": env["SUPABASE_ANON_KEY"], "Content-Type": "application/json"},
        {"email": email, "password": password},
    )
    if status != 200:
        raise AssertionError(f"Login failed for {email}: {status} {body}")
    cached = env["SUPABASE_URL"], env["SUPABASE_ANON_KEY"], body["access_token"]
    _auth_cache[email] = cached
    return cached


def call_edge_function(email, function_name, payload=None, *, via_script=False):
    """Call as a seeded user, optionally exercising the generated CLI caller."""
    payload = {} if payload is None else payload
    if via_script:
        result = subprocess.run(
            [
                sys.executable,
                "test-app/bin/dev-supabase-call-edge-function.py",
                email,
                function_name,
                json.dumps(payload),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if not result.stdout:
            raise AssertionError("Edge function caller did not print a JSON response")
        return result.returncode, json.loads(result.stdout)

    def invoke():
        api_url, anon_key, token = _auth(email)
        return _request_json(
            "POST",
            f"{api_url}/functions/v1/{function_name}",
            {
                "apikey": anon_key,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            payload,
        )

    status, body = invoke()
    if status == 401:
        _auth_cache.pop(email, None)
        status, body = invoke()
    return (0 if status < 400 else 1), {"status": status, "body": body}
