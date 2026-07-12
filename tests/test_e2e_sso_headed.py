"""
SSO Headed E2E Test (Playwright + CDP)

For each user (admin, user1):
  1. Start SSO environment; launch Chrome with SPNEGO + remote debugging
  2. Verify Keycloak account page loads within 30s (SSO authenticated)
  3. Navigate to app, log in via SSO, verify role in profile dialog
  4. Kill Chrome; delete user from Supabase
  5. Relaunch Chrome, repeat SSO login, verify role again
  6. Assert via Supabase API that user is Keycloak-only (no email/password identity)

Requirements:
  - App running (npm start):  cd test-app/frontend && npm start
  - Run explicitly:           python -m pytest tests/test_e2e_sso_headed.py
"""
import os
import re
import subprocess
import time
import pytest
import psycopg2
import requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError

_env_num = int(os.environ.get('UBK_DEV_ENV_NUM', '0'))
_base = 3000 + 100 * _env_num
CDP_PORT = _base + 2
APP_URL = f"http://localhost:{_base}/#/admin"
BIN_DIR = Path(__file__).parent.parent / "test-app" / "bin"


@pytest.fixture(scope="module", autouse=True)
def require_explicit_run(request):
    """Skip unless this file is explicitly specified on the command line."""
    if not any("test_e2e_sso_headed" in str(a) for a in request.config.args):
        pytest.skip("SSO headed test — run explicitly: python -m pytest tests/test_e2e_sso_headed.py")


@pytest.fixture(scope="module")
def sso_chrome():
    """Start SSO environment and launch Chrome with remote debugging."""
    print("\n[sso] Starting SSO environment (dev-sso-start.py)...")
    result = subprocess.run(["python", str(BIN_DIR / "dev-sso-start.py")])
    if result.returncode != 0:
        pytest.fail("dev-sso-start.py failed — see output above.")
    yield


# ── Helpers ──────────────────────────────────────────────────────────────────

def _launch_chrome(user=None):
    cmd = ["python", str(BIN_DIR / "dev-sso-chrome.py")]
    if user:
        cmd.append(user)
    cmd.append("--remote-debug")
    print(f"[sso] Launching Chrome as {user or 'default user'}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"dev-sso-chrome.py failed:\n{result.stderr.strip()}")
    time.sleep(3)
    print("[sso] chrome launched")


def _close_chrome():
    """Kill the Chrome process bound to the CDP port (pkill is reliable; browser.close() via CDP is not)."""
    result = subprocess.run(
        ["pkill", "-f", f"remote-debugging-port={CDP_PORT}"],
        capture_output=True,
    )
    time.sleep(2)
    if result.returncode == 0:
        print("[sso] Chrome process killed.")
    else:
        print("[sso] No Chrome process found to kill.")
    print("[sso] chrome closed")


def _find_real_page(browser):
    """Return first non-internal Chrome page, polling up to 10s."""
    deadline = time.time() + 10
    while time.time() < deadline:
        for ctx in browser.contexts:
            for p in ctx.pages:
                if not p.url.startswith("chrome://"):
                    return p
        time.sleep(0.3)
    all_urls = [p.url for ctx in browser.contexts for p in ctx.pages]
    pytest.fail(f"No Chrome tab found after 10s. Pages: {all_urls}")


def _complete_profile_dialog_if_shown(page):
    """Fill the post-login profile gate when it pops up.

    A profile that predates the SSO claims (e.g. auto-created by a seeded
    password login without metadata) misses its mandatory names, so the
    "Complete your profile" dialog legitimately appears and blocks the UI.
    Fill it like a real user. Marker values, not the Keycloak names: a fresh
    SSO profile must be created with the claim values and never show the
    dialog, so if _assert_profile_names_from_sso later sees these markers it
    means the gate wrongly appeared for a fresh profile.
    """
    dialog_title = page.get_by_text("Complete your profile")
    try:
        dialog_title.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeoutError:
        return
    print("[sso] Profile completion dialog shown — filling mandatory fields")
    page.get_by_label("First name").fill("Manual")
    page.get_by_label("Last name").fill("Fill")
    page.get_by_role("button", name="Save").click()
    dialog_title.wait_for(state="hidden", timeout=10000)
    print("[sso] Profile completion dialog saved and closed")


def _sso_login_and_verify_role(browser, email, expected_role, print_reminder=False):
    """Verify KC SSO, log in to app, assert role in profile dialog."""
    page = _find_real_page(browser)
    page.set_default_timeout(10000)

    expect(page).to_have_url(re.compile(r"keycloak\.dev\.local.*\/account"), timeout=30000)
    print(f"\n[sso] Keycloak authenticated for {email}. URL: {page.url}")

    if print_reminder:
        print(f"\n[sso] REMINDER: npm start must be running on {APP_URL}")

    page.goto(APP_URL)
    print(f"[sso] Gone to {APP_URL}")

    user_label = page.locator("header").get_by_text(email)
    try:
        user_label.wait_for(state="visible", timeout=5000)
        print(f"[sso] Already logged in as {email}")
    except PlaywrightTimeoutError:
        page.get_by_role("button", name="Login with SSO").click()
        print(f"[sso] Clicked Login with SSO")
        time.sleep(2)
        user_label.wait_for(state="visible", timeout=30000)
        print(f"[sso] Logged in via SSO. {email} visible in header.")

    _complete_profile_dialog_if_shown(page)
    user_label.click()
    page.get_by_role("menuitem", name="Profile").click()
    expect(page.get_by_role("dialog").get_by_text(expected_role, exact=True)).to_be_visible(timeout=5000)
    print(f"[sso] Profile shows '{expected_role}' role. ✓")


def _supabase_admin(path, method="GET", **kwargs):
    load_dotenv(os.path.abspath("test-app/backend/.env"))
    api_url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    assert api_url and key, "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY"
    headers = {"Authorization": f"Bearer {key}", "apikey": key}
    resp = requests.request(method, f"{api_url}/auth/v1/admin{path}", headers=headers, **kwargs)
    resp.raise_for_status()
    return resp


def _find_supabase_user(email):
    users = _supabase_admin("/users").json().get("users", [])
    return next((u for u in users if u["email"] == email), None)


def _delete_supabase_user(email):
    user = _find_supabase_user(email)
    assert user, f"User {email} not found in Supabase"
    _supabase_admin(f"/users/{user['id']}", method="DELETE")
    print(f"[sso] Deleted Supabase user: {email}")


def _get_profile_state(email, profile_concept="customer"):
    """Return (user_id, profile_id, profile_user_uuid) for the given email via direct DB access."""
    load_dotenv(os.path.abspath("test-app/backend/.env"))
    db_url = os.getenv("DB_URL")
    if not db_url:
        return None
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM auth.users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            return None
        user_id = row[0]
        cur.execute(
            f'SELECT id, "_user" FROM {psycopg2.extensions.quote_ident(profile_concept, cur)} WHERE "_user" = %s',
            (user_id,),
        )
        row = cur.fetchone()
        profile_id = row[0] if row else None
        profile_user = row[1] if row else None
    conn.close()
    return {"user_id": user_id, "profile_id": profile_id, "profile_user": profile_user}


def _assert_profile_names_from_sso(email, profile_concept):
    """The auto-created profile must carry the names Keycloak sends in the OIDC claims.

    dev-sso-start.py provisions users with firstName=<username capitalized> and
    lastName="Dev"; they reach Supabase as given_name/family_name user_metadata and
    fill the profile fields with default from_metadata(..., given_name/family_name).
    """
    username = email.split("@")[0]
    load_dotenv(os.path.abspath("test-app/backend/.env"))
    conn = psycopg2.connect(os.getenv("DB_URL"))
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT p."first_name", p."last_name", u.raw_user_meta_data '
            f'FROM {psycopg2.extensions.quote_ident(profile_concept, cur)} p '
            f'JOIN auth.users u ON u.id = p."_user" WHERE u.email = %s',
            (email,),
        )
        row = cur.fetchone()
    conn.close()
    assert row, f"No linked {profile_concept} profile found for {email}"
    first_name, last_name, metadata = row
    assert first_name == username.capitalize() and last_name == "Dev", (
        f"Profile names should come from the SSO token (expected "
        f"{username.capitalize()!r}/'Dev', got {first_name!r}/{last_name!r}). "
        f"user_metadata keys: {sorted((metadata or {}).keys())}"
    )
    print(f"[sso] Profile names filled from SSO claims: {first_name} {last_name} ✓")


def _assert_keycloak_only(email):
    user = _find_supabase_user(email)
    assert user, f"User {email} not found in Supabase"

    providers = user.get("app_metadata", {}).get("providers", [])
    assert providers == ["keycloak"], f"Expected ['keycloak'] providers, got: {providers}"

    # Supabase stores identities=null for pure SSO users (no local password identity).
    identities = user.get("identities") or []
    non_keycloak = [i["provider"] for i in identities if i["provider"] != "keycloak"]
    assert not non_keycloak, f"Found non-keycloak identities: {non_keycloak}"

    label = "null (pure SSO)" if user.get("identities") is None else identities
    print(f"[sso] {email} is Keycloak-only. providers={providers}, identities={label} ✓")


def _full_sso_cycle(playwright, email, expected_role, user_arg=None, print_reminder=False, profile_concept=None):
    """
    Round 1 → login + verify role
    Kill Chrome → delete from Supabase
    Round 2 → re-login + verify role
    API check → Keycloak-only
    If profile_concept is given, also verifies profile sync behaviour across the delete+re-create.
    Chrome stays open after round 2; caller is responsible for closing it.
    """
    browser = playwright.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    _sso_login_and_verify_role(browser, email, expected_role, print_reminder=print_reminder)

    before = _get_profile_state(email, profile_concept) if profile_concept else None
    if before:
        print(f"[sso] Before delete: user_id={before['user_id']}, profile_id={before['profile_id']}")

    _close_chrome()
    _delete_supabase_user(email)

    _launch_chrome(user=user_arg)
    browser2 = playwright.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    _sso_login_and_verify_role(browser2, email, expected_role)
    _assert_keycloak_only(email)
    if profile_concept:
        # Round 2 is guaranteed a fresh auth user + fresh profile, so the names
        # must have been filled from the Keycloak claims at creation.
        _assert_profile_names_from_sso(email, profile_concept)

    if before and before["profile_id"] is not None:
        after = _get_profile_state(email, profile_concept)
        assert after is not None, f"Could not read profile state after re-login for {email}"

        # New UUID means new profile; old orphaned profile is deactivated by same-email login.
        assert str(after["user_id"]) != str(before["user_id"]), \
            "Re-created SSO user should have a new UUID"
        assert after["profile_id"] != before["profile_id"], \
            "New UUID should get a fresh profile, not reuse the old one"
        assert after["profile_user"] == after["user_id"], \
            "New profile should be linked to the new UUID"

        # Old profile must still exist with the previous UUID saved.
        load_dotenv(os.path.abspath("test-app/backend/.env"))
        conn = psycopg2.connect(os.getenv("DB_URL"))
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT "_user", "_user_prev" FROM {psycopg2.extensions.quote_ident(profile_concept, cur)} WHERE id = %s',
                (before["profile_id"],),
            )
            old_row = cur.fetchone()
        conn.close()
        assert old_row is not None, "Old profile record must still exist after user deletion (no FK cascade)"
        assert old_row[0] is None, "Old profile should be deactivated after same-email new-UUID login"
        assert str(old_row[1]) == str(before["user_id"]), "Old profile should keep the previous UUID"
        print(f"[sso] After re-login: old profile {before['profile_id']} deactivated, "
              f"new profile {after['profile_id']} linked to new UUID {after['user_id']} ✓")

    _close_chrome()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_sso_admin_profile(sso_chrome):
    with sync_playwright() as playwright:
        _launch_chrome(user="admin")
        _full_sso_cycle(playwright, "admin@test.com", "admin", print_reminder=True)
    # Chrome from round 2 stays open; test_sso_user1_profile will close it.


def test_sso_user1_profile(sso_chrome):
    with sync_playwright() as playwright:
        _launch_chrome(user="user1")
        _full_sso_cycle(playwright, "user1@test.com", "user", user_arg="user1", profile_concept="customer")
