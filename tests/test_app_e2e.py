"""
Browser E2E Tests (Playwright)

All tests in this file require a running frontend server (--slow flag).
They interact exclusively through the browser — no direct API calls.
"""

import pytest
import os
import time
import json
from playwright.sync_api import Page, expect
from xprocess import ProcessStarter
from smtp_mock import smtp_emails as _smtp_emails, smtp_lock as _smtp_lock, extract_links as _extract_links


@pytest.fixture(scope="module")
def app_server(xprocess, request):
    if not request.config.getoption("--slow"):
        pytest.skip("need --slow option to run")

    frontend_dir = os.path.abspath("test-app/frontend")

    # Build the production bundle first (Vite dev server has issues with
    # emotion/MUI pre-bundling in dev mode; the production build works correctly)
    import subprocess
    result = subprocess.run(
        ["npm", "run", "build", "--prefix", frontend_dir],
        capture_output=True, text=True, cwd=frontend_dir
    )
    if result.returncode != 0:
        pytest.fail(f"Frontend build failed:\n{result.stderr}")

    class Starter(ProcessStarter):
        pattern = "Local:"
        env = os.environ.copy()
        args = ["npm", "--prefix", frontend_dir, "run", "preview", "--", "--port", "3005"]
        cwd = frontend_dir
        timeout = 30

    # Always restart so the freshly built bundle is served
    try:
        xprocess.getinfo("app_server_pure").terminate()
    except Exception:
        pass

    xprocess.ensure("app_server_pure", Starter)
    yield "http://localhost:3005"
    xprocess.getinfo("app_server_pure").terminate()


def test_create_product_as_user(page: Page, app_server):
    """
    Pure E2E test: No mocks, no interceptions.
    Acts as a real user creating a product.
    """
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        admin_user = next(u for u in json.load(f)["users"] if "admin" in u["roles"])

    page.set_default_timeout(10000)
    page.goto(app_server)
    page.wait_for_timeout(3000)

    # Login
    page.locator('input[name="email"]').fill(admin_user["email"])
    page.locator('input[name="password"]').fill(admin_user["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Catalog")).to_be_visible()

    # Go to Products → Create
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    page.get_by_label("Create").click()
    page.wait_for_url("**#/product/create**")
    page.locator('input[name="name"]').wait_for(state="visible")

    # Fill product details
    page.locator('input[name="name"]').fill("_User Journey Product")
    page.locator('input[name="price"]').fill("49.99")
    page.locator('input[name="stock_quantity"]').fill("100")
    page.locator('input[name="sku"]').fill("PURE-E2E-001")
    page.get_by_label("Status").click()
    page.get_by_role("option", name="published").click()
    page.get_by_label("Save").click()
    page.wait_for_timeout(1000)

    # Verify in list
    page.get_by_role("menuitem", name="Products").click()
    page.get_by_role("button", name="Name").click()
    page.wait_for_timeout(500)
    expect(page.get_by_role("cell", name="_User Journey Product").first).to_be_visible()
    expect(page.get_by_role("cell", name="PURE-E2E-001").first).to_be_visible()

    # Verify Relations tab
    page.get_by_role("row", name="_User Journey Product").click()
    page.get_by_role("tab", name="Relations").click()
    expect(page.get_by_label("Categories")).to_be_visible()


def test_create_order_and_upload_document_as_user(page: Page, app_server):
    """
    E2E test as user1: create an order in 'initial' state and upload a document.
    Verifies the full document upload flow works end-to-end from the browser.
    """
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        users = json.load(f)["users"]
    user1 = next(u for u in users if "user" in u["roles"])

    page.set_default_timeout(10000)
    page.goto(app_server)
    page.wait_for_timeout(2000)

    # Login as user1
    page.locator('input[name="email"]').fill(user1["email"])
    page.locator('input[name="password"]').fill(user1["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Sales")).to_be_visible()

    # Navigate to Orders → Create
    page.get_by_text("Sales").click()
    page.get_by_role("menuitem", name="Orders").click()
    page.get_by_label("Create").click()
    page.wait_for_url("**#/order/create**")

    # Fill the order form
    page.locator('input[name="order_date"]').fill("2024-01-15")
    page.locator('input[name="total_amount"]').fill("99.99")
    page.locator('input[name="shipping_address"]').fill("_E2E Test Order Address")
    # Select first available customer from the MUI Select dropdown
    page.get_by_label("Customer *").click()
    page.get_by_role("option").first.click()

    page.get_by_label("Save").click()
    # Wait for redirect to the edit page (URL contains a numeric order ID)
    page.wait_for_url(lambda url: bool(__import__('re').search(r'#/order/\d+', url)), timeout=10000)
    page.wait_for_load_state("networkidle")

    # Go to Documents tab
    page.get_by_role("tab", name="Documents").click()
    page.wait_for_timeout(500)

    import uuid
    unique_name = f"e2e_invoice_{uuid.uuid4().hex[:8]}.txt"

    # Upload a file to the "invoice" tag (first file input)
    file_input = page.locator('input[type="file"]').first
    file_input.set_input_files({
        "name": unique_name,
        "mimeType": "text/plain",
        "buffer": b"E2E test invoice content",
    })

    # Verify the filename appears in the Documents table (more reliable than catching the transient notification)
    expect(page.get_by_text(unique_name)).to_be_visible(timeout=10000)


def test_forgot_password_browser_flow(page: Page, app_server, smtp_server):
    """
    Full browser E2E test for the forgot-password flow — no direct API calls.
    1. Ensure clean login state (log out via UI if a previous test left a session)
    2. Click "Forgot password?", submit the form
    3. Capture the reset email from the in-process SMTP mock
    4. Navigate the browser to the recovery link
    5. Set a new password via the set-password form
    6. Verify Products data is accessible immediately (no reload required)
    7. Restore the original password via the in-app Change Password dialog
    """
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        admin_user = next(u for u in json.load(f)["users"] if "admin" in u["roles"])
    email = admin_user["email"]
    original_password = admin_user["password"]
    new_password = "BrowserResetTest999!"

    # Supabase site_url=http://localhost:3000 but test server is on 3005.
    # Intercept and rewrite port so the SPA receives the recovery tokens.
    test_port = app_server.split(":")[-1].rstrip("/")
    page.route(
        "http://localhost:3000/**",
        lambda route: route.continue_(url=route.request.url.replace("localhost:3000", f"localhost:{test_port}"))
    )

    # -- 1. Ensure we land on the login page.
    # The previous test may have left the user logged in; if so, log out via the
    # user menu so the session is clean before the forgot-password flow starts.
    page.goto(app_server)
    page.set_default_timeout(10000)
    page.wait_for_load_state("networkidle")
    # Use a more flexible selector for the user menu button
    user_menu = page.locator('header button[aria-haspopup="true"]')
    if user_menu.is_visible():
        user_menu.click()
        page.get_by_role("menuitem", name="Logout").click()
    expect(page.get_by_text("Forgot password?")).to_be_visible()

    # -- 2. Submit the forgot-password form
    with _smtp_lock:
        _smtp_emails.clear()

    page.get_by_text("Forgot password?").click()
    page.wait_for_url("**#/forgot-password**")
    page.get_by_role("button", name="Reset password").wait_for(state="visible")
    page.get_by_label("Email").fill(email)
    page.get_by_role("button", name="Reset password").click()
    print(f"\nReset password form submitted for: {email}")

    # -- 3. Wait for the reset email from the SMTP mock
    deadline = time.time() + 10
    email_received = None
    while time.time() < deadline:
        with _smtp_lock:
            matching = [e for e in _smtp_emails if email in e["rcpt_tos"]]
        if matching:
            email_received = matching[-1]
            break
        time.sleep(0.5)
    assert email_received, (
        "Reset email not received via in-process SMTP. "
        "Ensure Supabase is configured to use SMTP on port 3010 "
        "(see test-app/backend/supabase_config.toml)."
    )
    print("Reset email received.")

    # -- 4. Extract recovery link and navigate the browser to it
    links = _extract_links(email_received["content"])
    recovery_links = [l for l in links if any(k in l for k in ("recovery", "verify", "token"))]
    assert recovery_links, f"No recovery link found in email. All links: {links}"
    recovery_url = recovery_links[0]
    print(f"Recovery URL: {recovery_url}")

    page.goto(recovery_url)
    # index.jsx rewrites hash tokens → /#/set-password?access_token=...
    page.wait_for_url("**#/set-password**")
    print("Landed on set-password page.")

    try:
        # -- 5. Fill the new-password form
        page.get_by_label("Password").first.fill(new_password)
        page.get_by_label("Confirm password").fill(new_password)
        page.get_by_role("button", name="Save").click()

        # window.location.replace('/') triggers a full reload so the Supabase client
        # re-initialises from storage with the new session token.
        page.wait_for_url(lambda url: "#/set-password" not in url, timeout=20000)
        page.wait_for_load_state("networkidle", timeout=20000)
        print(f"Redirected to main app. URL: {page.url}")

        # -- 6. Navigate to Products and assert data is accessible immediately
        page.get_by_text("Catalog").click()
        page.get_by_role("menuitem", name="Products").click()
        page.wait_for_url("**#/product**")
        data_rows = page.locator("tbody tr")
        data_rows.first.wait_for(state="visible", timeout=10000)
        count = data_rows.count()
        assert count > 0, (
            "No products found after password reset — data is not accessible immediately. "
            "A page reload should not be required after SetPassword."
        )
        print(f"Data accessible: {count} product row(s) visible after password reset.")

        # -- 7. Restore original password via the in-app Change Password dialog.
        # The user is still logged in (with new_password). Use Profile → Change Password.
        page.wait_for_load_state("networkidle")
        # Try multiple common selectors for the User Menu button in React-Admin
        user_menu_btn = page.locator('header button[aria-haspopup="true"]')
        if not user_menu_btn.is_visible():
            user_menu_btn = page.get_by_label("Profile")
        if not user_menu_btn.is_visible():
            user_menu_btn = page.get_by_label("User profile")
        
        user_menu_btn.first.wait_for(state="visible", timeout=15000)
        user_menu_btn.first.click()
        page.get_by_role("menuitem", name="Profile").click()
        page.get_by_role("button", name="Change Password").click()
        page.get_by_label("Current Password").fill(new_password)
        page.get_by_label("New Password", exact=True).fill(original_password)
        page.get_by_label("Confirm New Password").fill(original_password)
        page.get_by_role("button", name="Update Password").click()
        page.get_by_text("Password updated successfully").wait_for(state="visible", timeout=10000)
        print(f"Original password restored for {email} via in-app Change Password.")
    finally:
        # Emergency restore via API if the UI flow failed
        # This ensures subsequent tests (and retries) have the correct password
        import requests
        from dotenv import load_dotenv
        load_dotenv("test-app/backend/.env")
        load_dotenv("test-app/frontend/.env")
        api_url = os.getenv("REACT_APP_SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if api_url and service_role_key:
            # 1. Get user ID
            headers = {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}
            users_resp = requests.get(f"{api_url}/auth/v1/admin/users", headers=headers)
            if users_resp.status_code == 200:
                users = users_resp.json().get("users", [])
                target_user = next((u for u in users if u["email"] == email), None)
                if target_user:
                    user_id = target_user["id"]
                    # 2. Update password
                    requests.put(
                        f"{api_url}/auth/v1/admin/users/{user_id}",
                        headers=headers,
                        json={"password": original_password}
                    )
                    print(f"Admin API: Password restoration heartbeat for {email}")
