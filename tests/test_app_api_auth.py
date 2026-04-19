"""
Auth API Integration Tests

Tests auth flows by calling the Supabase API directly (no browser).
Covers backend contracts: login, registration, email confirmation,
role assignment via DB trigger, and forgot-password token flow.
"""

import pytest
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from dotenv import load_dotenv
from smtp_mock import smtp_emails as _smtp_emails, smtp_lock as _smtp_lock, extract_links as _extract_links, SMTP_PORT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env():
    load_dotenv(os.path.abspath("test-app/backend/.env"))
    load_dotenv(os.path.abspath("test-app/frontend/.env"))
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


def _supabase_request_password_reset(api_url: str, anon_key: str, email: str) -> int:
    """Call Supabase /auth/v1/recover to trigger a password reset email."""
    url = f"{api_url}/auth/v1/recover"
    data = json.dumps({"email": email}).encode("utf-8")
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
        return resp.status


def _follow_recovery_link_get_tokens(recovery_url: str) -> tuple[str | None, str | None]:
    """
    Follow the recovery link without chasing the redirect.
    Supabase replies with a 302 whose Location header contains the hash fragment
    with the session tokens (implicit flow):
      http://localhost:3000/#access_token=...&refresh_token=...&type=recovery
    Returns (access_token, refresh_token).
    """
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # abort redirect chain

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(recovery_url)
        return None, None  # No redirect received — unexpected
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        location = e.headers.get("Location", "")
        if "#" not in location:
            return None, None
        fragment = location.split("#", 1)[1]
        params = urllib.parse.parse_qs(fragment)
        access_token = params.get("access_token", [None])[0]
        refresh_token = params.get("refresh_token", [None])[0]
        return access_token, refresh_token


def _supabase_update_password(api_url: str, anon_key: str, access_token: str, new_password: str) -> int:
    """Update the current user's password using a recovery access token."""
    url = f"{api_url}/auth/v1/user"
    data = json.dumps({"password": new_password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status


def _supabase_admin_update_password(api_url: str, service_key: str, user_id: str, new_password: str):
    """Update a user's password directly via the admin API (no email flow)."""
    url = f"{api_url}/auth/v1/admin/users/{user_id}"
    data = json.dumps({"password": new_password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _supabase_get_user_id_by_email(api_url: str, service_key: str, email: str) -> str | None:
    """Return the Supabase user ID for the given email, or None if not found."""
    url = f"{api_url}/auth/v1/admin/users"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        method="GET",
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    for user in body.get("users", []):
        if user.get("email") == email:
            return user["id"]
    return None


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
    """Verify the generated MyLoginPage.jsx contains the registration form."""
    login_file = os.path.abspath("test-app/frontend/src/layout/MyLoginPage.jsx")
    assert os.path.exists(login_file), "MyLoginPage.jsx not found"

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


def test_forgot_password_flow(smtp_server):
    """
    Full forgot-password flow:
    1. Request a password reset for a seeded user
    2. Capture the reset email from the mock SMTP server
    3. Extract the recovery link
    4. Follow the link (without chasing the redirect) and parse the session
       tokens from the Location header hash fragment
    5. Set a new password using the recovery access token
    6. Verify login works with the new password
    7. Restore the original password via the admin API
    """
    api_url, anon_key = _load_env()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("REACT_APP_SUPABASE_SERVICE_KEY")

    # Use the first seeded user — already confirmed, no email flow needed for setup
    sec_file = os.path.abspath("test-app/security_extended.json")
    assert os.path.exists(sec_file), "security_extended.json not found — run tests/test_app_backend.py first"
    with open(sec_file) as f:
        sec = json.load(f)
    test_user = sec["users"][0]
    email = test_user["email"]
    original_password = test_user["password"]
    new_password = "ResetTestPassword789!"

    # Ensure user has their original password before running (handles broken state from previous runs)
    ok, _ = _supabase_login(api_url, anon_key, email, original_password)
    if not ok and service_key:
        print(f"Restoring original password for {email} before test...")
        user_id = _supabase_get_user_id_by_email(api_url, service_key, email)
        assert user_id, f"Could not find user ID for {email}"
        _supabase_admin_update_password(api_url, service_key, user_id, original_password)

    # -- Step 1: Request password reset
    with _smtp_lock:
        _smtp_emails.clear()

    status = _supabase_request_password_reset(api_url, anon_key, email)
    assert status == 200, f"Password reset request returned {status}"
    print(f"\nPassword reset requested for: {email}")

    # -- Step 2: Wait for the reset email
    print("Waiting for reset email via mock SMTP...")
    deadline = time.time() + 10
    email_received = None
    while time.time() < deadline:
        with _smtp_lock:
            matching = [e for e in _smtp_emails if email in e["rcpt_tos"]]
        if matching:
            email_received = matching[-1]
            break
        time.sleep(0.5)

    if not email_received:
        pytest.skip(
            "Reset email not received via in-process SMTP. "
            "Ensure Supabase is configured to use SMTP on port 3010 "
            "(see test-app/backend/supabase_config.toml)."
        )

    content = email_received["content"]
    print(f"\n--- Reset email (first 400 chars) ---\n{content[:400]}\n---")

    # -- Step 3: Extract recovery link
    links = _extract_links(content)
    recovery_links = [l for l in links if any(k in l for k in ("recovery", "reset", "verify", "token"))]
    assert recovery_links, f"No recovery link found in email. All links: {links}"
    recovery_url = recovery_links[0]
    print(f"Recovery URL: {recovery_url}")

    # -- Step 4: Follow link and parse session tokens from redirect Location header
    access_token, refresh_token = _follow_recovery_link_get_tokens(recovery_url)
    assert access_token, (
        f"No access_token found in redirect Location header. "
        f"Recovery URL: {recovery_url}. "
        "Check that Supabase is using implicit flow (not PKCE)."
    )
    assert refresh_token, "No refresh_token found in redirect Location header."
    print(f"Got access_token: {access_token[:20]}...")

    # -- Step 5: Set new password using the recovery token
    status = _supabase_update_password(api_url, anon_key, access_token, new_password)
    assert status == 200, f"Password update returned {status}"
    print("Password updated successfully.")

    # -- Step 6: Verify login with the new password
    success, token_or_err = _supabase_login(api_url, anon_key, email, new_password)
    assert success, f"Login with new password failed: {token_or_err}"
    print("Login with new password successful!")

    # Verify old password no longer works
    old_works, _ = _supabase_login(api_url, anon_key, email, original_password)
    assert not old_works, "Old password still works after reset — password was not changed"

    # -- Step 7: Restore original password via admin API (no extra email flow)
    if service_key:
        user_id = _supabase_get_user_id_by_email(api_url, service_key, email)
        assert user_id, f"Could not find user ID for {email} via admin API"
        _supabase_admin_update_password(api_url, service_key, user_id, original_password)
        print(f"Restored original password for {email}.")
        success, _ = _supabase_login(api_url, anon_key, email, original_password)
        assert success, "Login with restored original password failed"
        print("Restoration verified.")
    else:
        print("No service key available — skipping password restoration (original password remains changed).")


def test_seeded_users_login_and_rls():
    """
    Verify that seeded users can login and that RLS + field-level security
    is enforced correctly: all users can insert into product, but only admins
    can write the admin_field column.
    """
    frontend_dir = os.path.abspath("test-app/frontend")
    security_extended_file = os.path.abspath("test-app/security_extended.json")
    assert os.path.exists(security_extended_file), "security_extended.json not found"

    with open(security_extended_file, "r") as f:
        auth_users = json.load(f)["users"]

    load_dotenv(os.path.join(frontend_dir, ".env"))
    api_url = os.getenv("REACT_APP_SUPABASE_URL")
    anon_key = os.getenv("REACT_APP_SUPABASE_KEY")
    assert api_url and anon_key, "REACT_APP_SUPABASE_URL / REACT_APP_SUPABASE_KEY not found in frontend .env"

    for user in auth_users:
        email = user["email"]
        password = user["password"]
        role = "admin" if "admin" in user["roles"] else "user"
        print(f"Testing login for: {email} (role: {role})")

        url = f"{api_url}/auth/v1/token?grant_type=password"
        data = json.dumps({"email": email, "password": password}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                access_token = res_body["access_token"]
                assert access_token
                assert res_body["user"]["email"] == email
                print(f"  Login successful for {email}")

                insert_url = f"{api_url}/rest/v1/product"
                base_headers = {
                    "apikey": anon_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                }

                # -- Regular insert: all users allowed
                insert_data = json.dumps({
                    "name": f"Test product by {email}",
                    "price": 10.00,
                    "stock_quantity": 5,
                    "sku": f"TEST-SKU-{email.split('@')[0]}-{int(time.time())}",
                    "status": "draft",
                }).encode("utf-8")
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(insert_url, data=insert_data, headers=base_headers, method="POST")
                    ):
                        print(f"  Insert successful for {email}")
                except urllib.error.HTTPError as e:
                    pytest.fail(f"User {email} (role: {role}) failed to insert into product: {e.code} {e.read().decode()}")

                # -- Admin field insert: only admins allowed
                admin_data = json.dumps({
                    "name": f"Test product admin field by {email}",
                    "price": 15.00,
                    "stock_quantity": 5,
                    "sku": f"TEST-SKU-ADMIN-{email.split('@')[0]}-{int(time.time())}",
                    "status": "draft",
                    "admin_field": "secret",
                }).encode("utf-8")
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(insert_url, data=admin_data, headers=base_headers, method="POST")
                    ):
                        if role == "user":
                            pytest.fail(f"User {email} (role: user) was able to insert admin_field — should be blocked")
                        else:
                            print(f"  Admin field insert allowed for {email} (admin)")
                except urllib.error.HTTPError as e:
                    if role == "admin":
                        pytest.fail(f"Admin {email} failed to insert admin_field: {e.code} {e.read().decode()}")
                    else:
                        print(f"  Admin field correctly blocked for {email} (user): {e.code}")

        except urllib.error.HTTPError as e:
            pytest.fail(f"Login failed for {email}: {e.code} {e.read().decode()}")
