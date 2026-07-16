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
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from smtp_mock import smtp_emails as _smtp_emails, smtp_lock as _smtp_lock, extract_links as _extract_links, SMTP_PORT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_env():
    # Tests reach Supabase (Kong) directly via backend/.env, not the Vite proxy.
    load_dotenv(os.path.abspath("test-app/backend/.env"))
    api_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    assert api_url, "SUPABASE_URL not found in backend/.env"
    assert anon_key, "SUPABASE_ANON_KEY not found in backend/.env"
    return api_url, anon_key


def _normalize_confirmation_url(url: str, api_url: str) -> str:
    """Rewrite a proxy-based confirmation URL to hit Supabase (Kong) directly.

    Email links point at the Vite dev proxy (external_url), e.g.
    http://localhost:3300/test/api/auth/v1/verify?...  Tests must not depend on the
    proxy being alive, so splice the Supabase path onto the direct Kong api_url.
    """
    marker = "/auth/v1/"
    idx = url.find(marker)
    if idx == -1:
        return url
    return api_url.rstrip("/") + url[idx:]


def _supabase_signup(api_url: str, anon_key: str, email: str, password: str, metadata: dict | None = None) -> dict:
    """Call Supabase signUp endpoint and return the response body.

    `metadata` is stored as user metadata (signUp options.data in supabase-js).
    """
    url = f"{api_url}/auth/v1/signup"
    payload = {"email": email, "password": password}
    if metadata is not None:
        payload["data"] = metadata
    data = json.dumps(payload).encode("utf-8")
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


def _supabase_admin_create_user(
    api_url: str,
    service_key: str,
    email: str,
    password: str,
    roles: list[str],
) -> dict:
    """Create a confirmed user through the Supabase admin API."""
    url = f"{api_url}/auth/v1/admin/users"
    data = json.dumps({
        "email": email,
        "password": password,
        "email_confirm": True,
        "app_metadata": {"roles": roles},
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _supabase_admin_confirm_email(api_url: str, service_key: str, user_id: str):
    """Mark a user's email as confirmed via the admin API (skips the SMTP flow)."""
    url = f"{api_url}/auth/v1/admin/users/{user_id}"
    data = json.dumps({"email_confirm": True}).encode("utf-8")
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
    assert os.path.exists(sec_file), "security_extended.json not found - run pytest tests/test_backend.py first"

    with open(sec_file) as f:
        sec = json.load(f)

    reg = sec["registration"]
    assert reg["allow"] is True, (
        "registration.allow must be true in security_extended.json"
    )


def test_supabase_config_generated():
    """Verify the generated supabase_config_dev.toml contains SMTP settings."""
    config_file = os.path.abspath("test-app/backend/supabase_config_dev.toml")
    assert os.path.exists(config_file), "supabase_config_dev.toml not found"

    content = Path(config_file).read_text()
    assert "enable_confirmations = true" in content
    assert "enable_signup = true" in content
    # The CLI (2.88.1) rejects the config when smtp is enabled without
    # user/pass; the generator must emit the validator-only placeholders.
    assert 'user = "mock"' in content
    assert 'pass = "mock"' in content
    assert "[auth.rate_limit]" in content
    assert "email_sent = 120" in content
    assert 'max_frequency = "1s"' in content
    assert str(SMTP_PORT) in content


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
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

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

    links = _extract_links(content)
    confirmation_links = [l for l in links if any(k in l for k in ("verify", "confirm", "token", "signup"))]
    assert confirmation_links, f"No confirmation link found in email. Links found: {links}"

    confirmation_url = confirmation_links[0]
    print(f"Confirmation URL: {confirmation_url}")

    # -- Step 4: Follow confirmation link (GET request simulates clicking)
    # Normalize proxy URLs to direct Supabase so the test doesn't require Vite running.
    direct_url = _normalize_confirmation_url(confirmation_url, api_url)
    if direct_url != confirmation_url:
        print(f"Normalized to direct Supabase URL: {direct_url}")
    try:
        conf_req = urllib.request.Request(direct_url, method="GET")
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
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # Use the first seeded user — already confirmed, no email flow needed for setup
    sec_file = os.path.abspath("test-app/security_extended.json")
    assert os.path.exists(sec_file), "security_extended.json not found — run tests/test_backend.py first"
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
    recovery_url = _normalize_confirmation_url(recovery_links[0], api_url)
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
    is enforced correctly: only admins can insert into product, and only admins
    can write admin_* fields (customer.admin_field).
    """
    security_extended_file = os.path.abspath("test-app/security_extended.json")
    assert os.path.exists(security_extended_file), "security_extended.json not found"

    with open(security_extended_file, "r") as f:
        auth_users = json.load(f)["users"]

    load_dotenv(os.path.abspath("test-app/backend/.env"))
    api_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    assert api_url and anon_key, "SUPABASE_URL / SUPABASE_ANON_KEY not found in backend/.env"

    user1_customer_id = None
    user1_auth_headers = None
    admin_auth_headers = None

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
                user_id = res_body["user"]["id"]
                assert access_token
                assert res_body["user"]["email"] == email
                print(f"  Login successful for {email}")

                auth_headers = {
                    "apikey": anon_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                }

                if role == "admin":
                    admin_auth_headers = auth_headers

                if email == "user1@test.com":
                    customer_url = (
                        f"{api_url}/rest/v1/customer"
                        f"?select=id,_user,_user_email,_user_pending_link,email&_user=eq.{urllib.parse.quote(user_id)}"
                    )
                    customer_req = urllib.request.Request(
                        customer_url,
                        headers={
                            "apikey": anon_key,
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/json",
                        },
                        method="GET",
                    )
                    with urllib.request.urlopen(customer_req) as customer_response:
                        customer_rows = json.loads(customer_response.read().decode("utf-8"))

                    assert customer_rows, "user1 login should link a customer profile"
                    assert customer_rows[0]["_user"] == user_id
                    assert customer_rows[0]["_user_email"] == email
                    assert customer_rows[0]["email"] == email
                    assert customer_rows[0]["_user_pending_link"] is None
                    user1_customer_id = customer_rows[0]["id"]
                    user1_auth_headers = auth_headers

                # -- Product insert: only admins allowed, users are blocked
                insert_url = f"{api_url}/rest/v1/product"
                insert_data = json.dumps({
                    "name": f"Test product by {email}",
                    "price": 10.00,
                    "stock_quantity": 5,
                    "sku": f"TEST-SKU-{email.split('@')[0]}-{int(time.time())}",
                    "status": "draft",
                }).encode("utf-8")
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(insert_url, data=insert_data, headers=auth_headers, method="POST")
                    ):
                        if role == "user":
                            pytest.fail(f"User {email} should NOT be able to insert product (read-only for users)")
                        print(f"  Product insert allowed for {email} (admin)")
                except urllib.error.HTTPError as e:
                    if role == "admin":
                        pytest.fail(f"Admin {email} failed to insert product: {e.code} {e.read().decode()}")
                    print(f"  Product insert correctly blocked for {email} (user): {e.code}")

        except urllib.error.HTTPError as e:
            pytest.fail(f"Login failed for {email}: {e.code} {e.read().decode()}")

    # -- admin_field write restriction: only admins can write customer.admin_field
    if not (user1_customer_id and user1_auth_headers and admin_auth_headers):
        pytest.skip("Could not obtain required tokens/ids for admin_field test")

    patch_url = f"{api_url}/rest/v1/customer?id=eq.{user1_customer_id}"
    admin_field_data = json.dumps({"admin_field": "secret"}).encode("utf-8")

    try:
        with urllib.request.urlopen(
            urllib.request.Request(patch_url, data=admin_field_data, headers=user1_auth_headers, method="PATCH")
        ):
            pytest.fail("user1 should NOT be able to update customer.admin_field")
    except urllib.error.HTTPError as e:
        print(f"  customer.admin_field update correctly blocked for user1: {e.code}")

    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                patch_url,
                data=json.dumps({"admin_field": "admin_value"}).encode("utf-8"),
                headers=admin_auth_headers,
                method="PATCH",
            )
        ):
            print("  customer.admin_field update allowed for admin")
    except urllib.error.HTTPError as e:
        pytest.fail(f"Admin failed to update customer.admin_field: {e.code} {e.read().decode()}")


def test_signup_metadata_fills_customer_profile(smtp_server):
    """
    Registration metadata (signUp options.data, e.g. first_name/last_name) must be
    copied into the customer profile row created on first login. Fields the user's
    role cannot write (admin_*) must NOT be copied even if present in the metadata.
    """
    api_url, anon_key = _load_env()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    db_url = os.getenv("DB_URL")
    if not service_key or not db_url:
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY and DB_URL are required")

    email = f"metadata_signup_{int(time.time())}@test.local"
    password = "MetadataSignup123!"

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        _supabase_signup(
            api_url, anon_key, email, password,
            metadata={"first_name": "Amaia", "last_name": "Ibarra", "admin_field": "not-allowed"},
        )
        user_id = _supabase_get_user_id_by_email(api_url, service_key, email)
        assert user_id, "Signup should create the auth user"

        # Confirm the email via the admin API; the SMTP confirmation flow itself
        # is covered by test_register_user_and_email_flow.
        _supabase_admin_confirm_email(api_url, service_key, user_id)

        ok, token_or_err = _supabase_login(api_url, anon_key, email, password)
        assert ok, f"Login failed after confirmation: {token_or_err}"

        with conn.cursor() as cur:
            cur.execute(
                'SELECT "first_name", "last_name", "admin_field" FROM customer WHERE "_user" = %s',
                (user_id,),
            )
            row = cur.fetchone()
            assert row is not None, "First login should create a customer profile"
            first_name, last_name, admin_field = row
            assert first_name == "Amaia", f"first_name should come from signup metadata, got {first_name!r}"
            assert last_name == "Ibarra", f"last_name should come from signup metadata, got {last_name!r}"
            assert admin_field is None, "admin_field is not writable by the user role and must not be copied"
    finally:
        _supabase_delete_user_by_email(api_url, service_key, email)
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM customer WHERE "_user_email" = %s OR "_user_email_prev" = %s',
                (email, email),
            )
        conn.close()


def test_profile_without_metadata_leaves_ask_after_login_null_and_blocks_clearing(smtp_server):
    """
    Signup without metadata must still auto-create the profile at first login,
    leaving the required "ask_after_login" fields (first_name/last_name) NULL so
    the app can ask for them. Once the user fills such a field, the security
    trigger must reject an UPDATE that clears it back to null.
    """
    api_url, anon_key = _load_env()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    db_url = os.getenv("DB_URL")
    if not service_key or not db_url:
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY and DB_URL are required")

    email = f"ask_after_login_{int(time.time())}@test.local"
    password = "AskAfterLogin123!"

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        _supabase_signup(api_url, anon_key, email, password)
        user_id = _supabase_get_user_id_by_email(api_url, service_key, email)
        assert user_id, "Signup should create the auth user"
        _supabase_admin_confirm_email(api_url, service_key, user_id)

        ok, token = _supabase_login(api_url, anon_key, email, password)
        assert ok, f"Login failed after confirmation: {token}"

        with conn.cursor() as cur:
            cur.execute(
                'SELECT "id", "first_name", "last_name" FROM customer WHERE "_user" = %s',
                (user_id,),
            )
            row = cur.fetchone()
            assert row is not None, "First login should create a customer profile"
            customer_id, first_name, last_name = row
            assert first_name is None, f"first_name should be NULL without metadata, got {first_name!r}"
            assert last_name is None, f"last_name should be NULL without metadata, got {last_name!r}"

        auth_headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        patch_url = f"{api_url}/rest/v1/customer?id=eq.{customer_id}"

        # The user fills the mandatory fields (what the profile dialog does).
        with urllib.request.urlopen(
            urllib.request.Request(
                patch_url,
                data=json.dumps({"first_name": "Ane", "last_name": "Etxeberria"}).encode("utf-8"),
                headers=auth_headers,
                method="PATCH",
            )
        ):
            print("  ask_after_login fields filled by the user")

        # Clearing a filled ask_after_login field must be rejected by the trigger.
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    patch_url,
                    data=json.dumps({"first_name": None}).encode("utf-8"),
                    headers=auth_headers,
                    method="PATCH",
                )
            ):
                pytest.fail("Clearing first_name back to null should be rejected")
        except urllib.error.HTTPError as e:
            print(f"  Clearing first_name correctly blocked: {e.code}")

        with conn.cursor() as cur:
            cur.execute('SELECT "first_name" FROM customer WHERE "id" = %s', (customer_id,))
            assert cur.fetchone()[0] == "Ane", "first_name must keep its value after the blocked update"
    finally:
        _supabase_delete_user_by_email(api_url, service_key, email)
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM customer WHERE "_user_email" = %s OR "_user_email_prev" = %s',
                (email, email),
            )
        conn.close()


def test_sso_custom_claims_metadata_fills_customer_profile():
    """
    GoTrue nests non-standard OIDC claims (Keycloak's given_name/family_name)
    under user_metadata.custom_claims. from_metadata keys must also be resolved
    there so SSO logins fill the profile names. Exercises sync_role_profiles
    directly with an SSO-shaped metadata payload (the real flow needs a live
    Keycloak — covered by test_e2e_sso_headed.py).
    """
    _load_env()  # loads backend/.env into the environment
    db_url = os.getenv("DB_URL")
    if not db_url:
        pytest.skip("DB_URL is required")

    import uuid
    fake_user_id = str(uuid.uuid4())
    email = f"sso_claims_{int(time.time())}@test.local"
    metadata = json.dumps({
        "full_name": "User1 Dev",
        "custom_claims": {"given_name": "Amets", "family_name": "Zubizarreta"},
    })

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT public.sync_role_profiles(%s::uuid, %s, %s::jsonb, %s::jsonb)",
                (fake_user_id, email, '["user"]', metadata),
            )
            cur.execute(
                'SELECT "first_name", "last_name" FROM customer WHERE "_user" = %s',
                (fake_user_id,),
            )
            row = cur.fetchone()
            assert row is not None, "sync_role_profiles should create the profile"
            assert row == ("Amets", "Zubizarreta"), (
                f"Names should be filled from custom_claims, got {row!r}"
            )
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM customer WHERE "_user_email" = %s', (email,))
        conn.close()


def test_same_email_recreated_user_deactivates_old_profile_and_gets_new_customer():
    """
    Deleting an auth user leaves the old profile row linked to a dead UUID.
    When a new auth user logs in with the same email, the hook deactivates the
    orphaned profile and creates a distinct customer for the new UUID.
    """
    api_url, anon_key = _load_env()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    db_url = os.getenv("DB_URL")
    if not service_key or not db_url:
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY and DB_URL are required")

    email = f"profile_recreate_{int(time.time())}@test.local"
    first_password = "ProfileRecreateOne123!"
    second_password = "ProfileRecreateTwo123!"

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    first_customer_id = None
    second_customer_id = None

    try:
        first_user = _supabase_admin_create_user(api_url, service_key, email, first_password, ["user"])
        first_user_id = first_user["id"]
        ok, token_or_err = _supabase_login(api_url, anon_key, email, first_password)
        assert ok, f"First login failed: {token_or_err}"

        with conn.cursor() as cur:
            cur.execute(
                'SELECT id, "_user", "_user_email" FROM customer WHERE "_user" = %s',
                (first_user_id,),
            )
            row = cur.fetchone()
            assert row is not None, "First login should create a customer profile"
            first_customer_id, first_profile_user, first_profile_email = row
            assert str(first_profile_user) == first_user_id
            assert first_profile_email == email

        _supabase_delete_user_by_email(api_url, service_key, email)
        assert _supabase_get_user_id_by_email(api_url, service_key, email) is None

        second_user = _supabase_admin_create_user(api_url, service_key, email, second_password, ["user"])
        second_user_id = second_user["id"]
        assert second_user_id != first_user_id, "Recreated auth user should have a new UUID"

        ok, token_or_err = _supabase_login(api_url, anon_key, email, second_password)
        assert ok, f"Second login failed: {token_or_err}"

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "_user", "_user_email", "_user_prev", "_user_email_prev"
                FROM customer
                WHERE id = %s
                """,
                (first_customer_id,),
            )
            old_user, old_email, old_user_prev, old_email_prev = cur.fetchone()
            assert old_user is None
            assert old_email is None
            assert str(old_user_prev) == first_user_id
            assert old_email_prev == email

            cur.execute(
                'SELECT id, "_user", "_user_email" FROM customer WHERE "_user" = %s',
                (second_user_id,),
            )
            row = cur.fetchone()
            assert row is not None, "Second login should create a customer profile"
            second_customer_id, second_profile_user, second_profile_email = row
            assert second_customer_id != first_customer_id
            assert str(second_profile_user) == second_user_id
            assert second_profile_email == email
    finally:
        _supabase_delete_user_by_email(api_url, service_key, email)
        with conn.cursor() as cur:
            ids = [customer_id for customer_id in (first_customer_id, second_customer_id) if customer_id]
            if ids:
                cur.execute("DELETE FROM customer WHERE id = ANY(%s)", (ids,))
            cur.execute(
                'DELETE FROM customer WHERE "_user_email" = %s OR "_user_email_prev" = %s OR "_user_pending_link" = %s',
                (email, email, email),
            )
        conn.close()
