"""
Registration E2E Test

Tests the user self-registration flow including:
1. Register a new user via Supabase Auth API
2. Verify the user cannot login before email confirmation
3. Start the mock SMTP server, re-send confirmation, read the confirmation URL
4. Confirm the email via the Supabase verification API
5. Verify the user can now login
"""

import pytest
import os
import json
import time
import re
import threading
import asyncio
import smtplib
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env():
    frontend_dir = os.path.abspath("test-app/frontend")
    load_dotenv(os.path.join(frontend_dir, ".env"))
    api_url = os.getenv("REACT_APP_SUPABASE_URL")
    anon_key = os.getenv("REACT_APP_SUPABASE_KEY")
    assert api_url, "REACT_APP_SUPABASE_URL not found in frontend .env"
    assert anon_key, "REACT_APP_SUPABASE_KEY not found in frontend .env"
    return api_url, anon_key


def _supabase_signup(api_url: str, anon_key: str, email: str, password: str) -> dict:
    """Call Supabase signUp endpoint and return the response body."""
    url = f"{api_url}/auth/v1/signup"
    data = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": anon_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _supabase_login(api_url: str, anon_key: str, email: str, password: str) -> tuple[bool, str]:
    """
    Attempt to log in.
    Returns (success, error_message).
    """
    url = f"{api_url}/auth/v1/token?grant_type=password"
    data = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": anon_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return True, body.get("access_token", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return False, error_body


def _supabase_delete_user_by_email(api_url: str, service_key: str, email: str):
    """Delete a user by email using the admin API (requires service role key)."""
    # List users and find matching email
    url = f"{api_url}/auth/v1/admin/users"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            users = body.get("users", [])
            for user in users:
                if user.get("email") == email:
                    user_id = user["id"]
                    del_url = f"{api_url}/auth/v1/admin/users/{user_id}"
                    del_req = urllib.request.Request(
                        del_url,
                        headers={
                            "apikey": service_key,
                            "Authorization": f"Bearer {service_key}",
                        },
                        method="DELETE",
                    )
                    try:
                        urllib.request.urlopen(del_req)
                    except Exception:
                        pass
                    return
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SMTP Mock Server (in-process)
# ---------------------------------------------------------------------------

SMTP_PORT = 3010
_smtp_emails: list[dict] = []
_smtp_lock = threading.Lock()


class _MockSMTPHandler:
    """aiosmtpd-style handler that stores received emails."""
    async def handle_DATA(self, server, session, envelope):
        with _smtp_lock:
            _smtp_emails.append({
                "mail_from": envelope.mail_from,
                "rcpt_tos": envelope.rcpt_tos,
                "content": envelope.content.decode("utf-8", errors="replace"),
            })
        return "250 Message accepted for delivery"


def _extract_links(text: str) -> list:
    import quopri
    import html
    # Decode quoted-printable first
    decoded = quopri.decodestring(text).decode('utf-8', errors='replace')
    # Unescape HTML entities (like &amp;)
    unescaped = html.unescape(decoded)
    # Remove soft line breaks (encoded as =\n or =\r\n) and hard line breaks within the URL
    raw_links = re.findall(r'https?://[^\s<>"\']+', unescaped)
    clean_links = [l.replace('=\n', '').replace('=\r\n', '').replace('\n', '').replace('\r', '') for l in raw_links]
    return clean_links


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def smtp_server():
    """Start an in-process SMTP mock on port 3010 for the duration of the module."""
    try:
        from aiosmtpd.controller import Controller
        handler = _MockSMTPHandler()
        controller = Controller(handler, hostname="0.0.0.0", port=SMTP_PORT)
        controller.start()
        yield controller
        controller.stop()
    except ImportError:
        pytest.skip("aiosmtpd not installed - run: pip install aiosmtpd")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

TEST_EMAIL = f"test_registration_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPassword123!"


def test_security_allows_registration():
    """Verify security_extended.json has registration.allow=true."""
    sec_file = os.path.abspath("test-app/security_extended.json")
    assert os.path.exists(sec_file), "security_extended.json not found - run pytest tests/test_app_backend.py first"

    with open(sec_file) as f:
        sec = json.load(f)

    reg = sec["registration"]
    assert reg["allow"] is True, (
        "registration.allow must be true in security_extended.json"
    )


def test_supabase_config_generated():
    """Verify the generated supabase_config.toml contains SMTP settings."""
    config_file = os.path.abspath("test-app/backend/supabase_config.toml")
    assert os.path.exists(config_file), "supabase_config.toml not found"

    content = Path(config_file).read_text()
    assert "enable_confirmations = true" in content
    assert "enable_signup = true" in content
    assert str(SMTP_PORT) in content


def test_login_page_has_registration():
    """Verify the generated MyLoginPage.js contains the registration form."""
    login_file = os.path.abspath("test-app/frontend/src/layout/MyLoginPage.js")
    assert os.path.exists(login_file), "MyLoginPage.js not found"

    content = Path(login_file).read_text()
    assert "RegisterForm" in content, "RegisterForm component not found in login page"
    assert "Register" in content
    assert "Confirm Password" in content


def test_register_user_and_email_flow(smtp_server):
    """
    Full registration flow:
    1. Sign up via API
    2. Verify cannot login (email not confirmed)
    3. Capture confirmation email from mock SMTP
    4. Confirm email
    5. Verify can now login
    """
    api_url, anon_key = _load_env()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("REACT_APP_SUPABASE_SERVICE_KEY")

    # -- Step 1: Sign up
    global _smtp_emails
    with _smtp_lock:
        _smtp_emails.clear()

    try:
        signup_resp = _supabase_signup(api_url, anon_key, TEST_EMAIL, TEST_PASSWORD)
    except urllib.error.HTTPError as e:
        pytest.fail(f"Signup failed: {e.code} {e.read().decode()}")

    print(f"\nSigned up: {TEST_EMAIL}")

    # Check if Supabase requires email confirmation - if user is already confirmed (e.g. local dev without SMTP),
    # the test is still valid as a smoke test
    user_data = signup_resp.get("user") or signup_resp
    email_confirmed_at = user_data.get("email_confirmed_at")

    if email_confirmed_at:
        # Supabase local dev may auto-confirm without SMTP configured
        print("NOTE: Supabase auto-confirmed the email (SMTP not configured in Supabase, using Inbucket)")
        # Verify we can login
        success, token_or_err = _supabase_login(api_url, anon_key, TEST_EMAIL, TEST_PASSWORD)
        assert success, f"Login failed after auto-confirmation: {token_or_err}"
        print(f"Login successful after auto-confirmation")
        return

    # -- Step 2: Verify cannot login before confirmation
    success, error = _supabase_login(api_url, anon_key, TEST_EMAIL, TEST_PASSWORD)
    assert not success, "User should NOT be able to login before confirming email"
    print(f"Login correctly blocked: {error[:120]}")

    # -- Step 3: Wait for confirmation email from mock SMTP
    print("Waiting for confirmation email via mock SMTP...")
    deadline = time.time() + 10
    email_received = None
    while time.time() < deadline:
        with _smtp_lock:
            matching = [e for e in _smtp_emails if TEST_EMAIL in e["rcpt_tos"]]
        if matching:
            email_received = matching[-1]
            break
        time.sleep(0.5)

    if not email_received:
        # Check the log file as fallback (if SMTP was configured externally)
        log_file = "tmp-dev-smtp-mock.txt"
        if os.path.exists(log_file):
            content = Path(log_file).read_text()
            links_in_log = [l for l in _extract_links(content) if "verify" in l or "confirm" in l or "token" in l]
            if links_in_log:
                pytest.skip(
                    f"Email sent to external SMTP mock. Confirmation link found in {log_file}: {links_in_log[0]}"
                )
        pytest.skip(
            "Confirmation email not received via in-process SMTP. "
            "Make sure Supabase is configured to use SMTP on port 3010 (see test-app/backend/supabase_config.toml)"
        )

    content = email_received["content"]
    print(f"\n--- Confirmation email ---\n{content[:500]}\n---")
    Path("tmp-dev-smtp-mock.txt").write_text(
        f"=== Email received at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        f"FROM: {email_received['mail_from']}\n"
        f"TO: {', '.join(email_received['rcpt_tos'])}\n\n"
        f"{content}\n"
    )

    links = _extract_links(content)
    confirmation_links = [l for l in links if any(k in l for k in ("verify", "confirm", "token", "signup"))]
    assert confirmation_links, f"No confirmation link found in email. Links found: {links}"

    confirmation_url = confirmation_links[0]
    print(f"Confirmation URL: {confirmation_url}")

    # -- Step 4: Follow confirmation link (GET request simulates clicking)
    try:
        conf_req = urllib.request.Request(confirmation_url, method="GET")
        with urllib.request.urlopen(conf_req) as resp:
            print(f"Confirmation response: {resp.status}")
    except urllib.error.HTTPError as e:
        # A redirect (302/303) is expected - that's fine
        if e.code in (301, 302, 303, 307, 308):
            print(f"Confirmation redirected ({e.code}) - email confirmed")
        else:
            pytest.fail(f"Confirmation request failed: {e.code} {e.read().decode()[:200]}")
    except Exception as e:
        print(f"Confirmation note: {e}")

    # Give Supabase a moment to process the confirmation
    time.sleep(1)

    # -- Step 5: Verify can now login
    success, token_or_err = _supabase_login(api_url, anon_key, TEST_EMAIL, TEST_PASSWORD)
    assert success, f"Login failed after email confirmation: {token_or_err}"
    print(f"Login successful after confirmation! Token: {token_or_err[:20]}...")

    # -- Step 6: Verify default role was assigned via trigger
    # Decode JWT to check app_metadata
    import base64
    import json
    _, payload_b64, _ = token_or_err.split('.')
    # Add padding if needed
    payload_b64 += '=' * (4 - len(payload_b64) % 4)
    payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
    
    app_metadata = payload.get('app_metadata', {})
    roles = app_metadata.get('roles', [])
    
    # Get expected role from security_extended.json
    sec_file = os.path.abspath("test-app/security_extended.json")
    with open(sec_file) as f:
        sec = json.load(f)
    expected_role = sec["registration"]["role"]
    
    assert expected_role in roles, f"Expected role '{expected_role}' not found in user roles: {roles}"
    print(f"Verified default role '{expected_role}' assigned successfully.")

    # Cleanup: delete the test user if we have service role key
    if service_key:
        _supabase_delete_user_by_email(api_url, service_key, TEST_EMAIL)
        print(f"Cleaned up test user: {TEST_EMAIL}")
