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

_env_num = int(os.environ.get('UBK_DEV_ENV_NUM', '0'))
_base = 3000 + 100 * _env_num
_FRONTEND_PORT = _base + 0
_PREVIEW_PORT = _base + 1

# Optional second dev environment (UBK_DEV_MODEL), served on a +50 port offset.
from conftest import (
    HAS_SECONDARY_MODEL,
    SECONDARY_MODEL,
    SECONDARY_BASE,
    SECONDARY_PREVIEW_PORT as _DUMMY_PREVIEW_PORT,
)


@pytest.fixture(scope="module")
def app_server(xprocess, request):
    if not request.config.getoption("--slow"):
        pytest.skip("need --slow option to run")

    frontend_dir = os.path.abspath("test-app/frontend")

    # Build the production bundle first (Vite dev server has issues with
    # emotion/MUI pre-bundling in dev mode; the production build works correctly)
    import subprocess
    result = subprocess.run(
        ["npm", "run", "build", "--prefix", frontend_dir, "--", "--mode", "development"],
        capture_output=True, text=True, cwd=frontend_dir
    )
    if result.returncode != 0:
        pytest.fail(f"Frontend build failed:\n{result.stderr}")

    # `vite preview` serves the production build and proxies /api -> Kong (preview.proxy
    # in vite.config.js). The app resolves VITE_SUPABASE_URL against this same origin,
    # so a single server is enough — no separate dev server needed.
    class Starter(ProcessStarter):
        pattern = "Local:"
        env = os.environ.copy()
        args = ["npm", "--prefix", frontend_dir, "run", "preview", "--", "--port", str(_PREVIEW_PORT)]
        cwd = frontend_dir
        timeout = 30

    # Always restart so the freshly built bundle is served
    try:
        xprocess.getinfo("app_server_pure").terminate()
    except Exception:
        pass

    xprocess.ensure("app_server_pure", Starter)
    yield f"http://localhost:{_PREVIEW_PORT}"
    xprocess.getinfo("app_server_pure").terminate()


@pytest.fixture(scope="module")
def secondary_app_server(xprocess, request):
    """Build and serve the second dev environment's frontend on the +50 preview port."""
    if not request.config.getoption("--slow"):
        pytest.skip("need --slow option to run")
    if not HAS_SECONDARY_MODEL:
        pytest.skip("UBK_DEV_MODEL is not set; secondary dev environment disabled")

    frontend_dir = os.path.abspath(f"{SECONDARY_MODEL}/frontend")

    import subprocess
    result = subprocess.run(
        ["npm", "run", "build", "--prefix", frontend_dir, "--", "--mode", "development"],
        capture_output=True, text=True, cwd=frontend_dir
    )
    if result.returncode != 0:
        pytest.fail(f"Secondary frontend build failed:\n{result.stderr}")

    class Starter(ProcessStarter):
        pattern = "Local:"
        env = os.environ.copy()
        args = ["npm", "--prefix", frontend_dir, "run", "preview", "--", "--port", str(_DUMMY_PREVIEW_PORT)]
        cwd = frontend_dir
        timeout = 30

    try:
        xprocess.getinfo("secondary_app_server_pure").terminate()
    except Exception:
        pass

    xprocess.ensure("secondary_app_server_pure", Starter)
    yield f"http://localhost:{_DUMMY_PREVIEW_PORT}"
    xprocess.getinfo("secondary_app_server_pure").terminate()


def test_secondary_app_server_responds(secondary_app_server):
    """Minimal smoke test: the second environment's frontend serves HTTP 200."""
    import urllib.request

    with urllib.request.urlopen(secondary_app_server + "/", timeout=15) as resp:
        assert resp.status == 200, f"Secondary app server returned {resp.status}"
        body = resp.read().decode("utf-8", errors="replace")
    assert "<div id=\"root\">" in body or "<title>" in body, (
        "Secondary app server response did not look like the SPA index page"
    )


def test_b2c_storefront_purchase_with_payment(page: Page, secondary_app_server):
    """
    Full storefront purchase flow on the b2c secondary app, browser only:
    sign in (storefront page) → add to cart → checkout details (address combos,
    shipping) → dev-mode card payment → "Order placed!". Then verify in the DB
    that the order is confirmed and paid.

    Skipped unless UBK_DEV_MODEL=b2c-app and its Supabase backend is running.
    """
    import re
    import urllib.request
    import urllib.error

    if not HAS_SECONDARY_MODEL:
        pytest.skip("b2c storefront test requires UBK_DEV_MODEL=b2c-app")
    if SECONDARY_MODEL != "b2c-app":
        pytest.skip("b2c storefront test requires UBK_DEV_MODEL=b2c-app")

    backend = f"http://localhost:{SECONDARY_BASE + 40}"
    try:
        urllib.request.urlopen(backend + "/auth/v1/health", timeout=5)
    except urllib.error.HTTPError:
        pass  # 401/404 still proves Kong is up
    except Exception:
        pytest.skip(f"b2c Supabase backend not reachable at {backend}")

    with open(os.path.abspath(f"{SECONDARY_MODEL}/security_extended.json")) as f:
        user1 = next(u for u in json.load(f)["users"] if "user" in u["roles"])

    page.set_default_timeout(15000)
    page.goto(secondary_app_server + "/b2c/#/")

    # -- Sign in through the storefront page (not the admin login)
    page.get_by_role("link", name="Log in").click()
    page.get_by_label("Email").fill(user1["email"])
    page.get_by_label("Password").fill(user1["password"])
    page.get_by_role("button", name="Sign in").click()

    # Back on the storefront with a session: catalog with Add to cart buttons.
    add_button = page.get_by_role("button", name="Add to cart").first
    add_button.wait_for(state="visible")
    add_button.click()

    # Cart drawer opens; go to checkout.
    page.get_by_role("button", name="Checkout").click()

    # -- Checkout details
    page.get_by_label("First name *").fill("E2E")
    page.get_by_label("Last name *").fill("Shopper")
    page.get_by_label("Address *").fill("Gran Via 1")
    page.get_by_label("Postal code *").fill("48001")

    # Cascading combos in DOM order: City, State/Province, Country.
    # Select country first so the cascade narrows the other two.
    combos = page.get_by_placeholder("Select or type…")
    combos.nth(2).click()
    page.get_by_role("listitem").filter(has_text="Spain").first.click()
    combos.nth(1).click()
    page.get_by_role("listitem").filter(has_text="Bizkaia").first.click()
    combos.nth(0).click()
    page.get_by_role("listitem").filter(has_text="Bilbao").first.click()

    page.get_by_role("button", name=re.compile(r"^Continue to payment")).click()

    # -- Payment step (dev simulator, card prefilled with the success test card)
    expect(page.get_by_text("Test mode")).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Pay ")).click()

    expect(page.get_by_text("Order placed!")).to_be_visible(timeout=30000)

    # -- DB check: latest order for the flow is confirmed and paid.
    import psycopg2
    from dotenv import dotenv_values
    db_url = dotenv_values(f"{SECONDARY_MODEL}/backend/.env").get("DB_URL")
    assert db_url, f"DB_URL not found in {SECONDARY_MODEL}/backend/.env"
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "state", "payment_status", "payment_reference", '
                '"shipping_address_first_name", "shipping_address_last_name" '
                'FROM "order" ORDER BY "id" DESC LIMIT 1;'
            )
            state, payment_status, payment_reference, first_name, last_name = cur.fetchone()
            assert state == "confirmed", f"Expected confirmed order, got {state}"
            assert payment_status == "paid", f"Expected paid order, got {payment_status}"
            assert payment_reference and payment_reference.startswith("pi_dev_")
            assert (first_name, last_name) == ("E2E", "Shopper")
    finally:
        conn.close()


def test_create_product_as_user(page: Page, app_server):
    """
    Pure E2E test: No mocks, no interceptions.
    Acts as a real user creating a product.
    """
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        admin_user = next(u for u in json.load(f)["users"] if "admin" in u["roles"])

    page.set_default_timeout(10000)
    page.goto(app_server + "/#/admin")
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
    page.wait_for_url("**#/admin/product/create**")
    page.locator('input[name="name"]').wait_for(state="visible")

    # Fill product details
    page.locator('input[name="name"]').fill("_User Journey Product")
    page.locator('input[name="price"]').fill("49.99")
    page.locator('input[name="stock_quantity"]').fill("100")
    page.locator('input[name="sku"]').fill("PURE-E2E-001")
    page.get_by_role("combobox", name="Status").click()
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
    expect(page.get_by_role("combobox", name="Categories")).to_be_visible()


def test_profile_completion_dialog_asks_for_missing_fields(page: Page, app_server):
    """
    E2E test of the post-login profile gate: customer.first_name/last_name are
    required "ask_after_login", so a user whose profile misses them gets a
    blocking dialog right after login. Filling it saves the values and unblocks
    the admin UI; the dialog must not reappear on reload.

    Runs before the other user1 tests so they always find a completed profile.
    """
    import psycopg2
    from dotenv import dotenv_values

    with open(os.path.abspath("test-app/security_extended.json")) as f:
        users = json.load(f)["users"]
    user1 = next(u for u in users if "user" in u["roles"])

    # Clear the names directly in the DB so the gate state is deterministic
    # (a system connection bypasses the security trigger's no-clearing guard).
    db_url = dotenv_values("test-app/backend/.env").get("DB_URL")
    assert db_url, "DB_URL not found in test-app/backend/.env"
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE customer SET "first_name" = NULL, "last_name" = NULL '
                'WHERE "_user_email" = %s',
                (user1["email"],),
            )

        page.set_default_timeout(10000)
        page.goto(app_server + "/#/admin")
        page.wait_for_timeout(2000)

        page.locator('input[name="email"]').fill(user1["email"])
        page.locator('input[name="password"]').fill(user1["password"])
        page.get_by_role("button", name="Sign in").click()

        # The gate blocks the admin UI until the mandatory fields are filled.
        expect(page.get_by_text("Complete your profile")).to_be_visible()
        page.get_by_label("First name").fill("Gate")
        page.get_by_label("Last name").fill("Tested")
        page.get_by_role("button", name="Save").click()
        expect(page.get_by_text("Complete your profile")).not_to_be_visible()

        with conn.cursor() as cur:
            cur.execute(
                'SELECT "first_name", "last_name" FROM customer WHERE "_user_email" = %s',
                (user1["email"],),
            )
            assert cur.fetchone() == ("Gate", "Tested"), "Dialog must save the profile fields"

        # A completed profile must not trigger the dialog again.
        page.reload()
        page.wait_for_timeout(2000)
        expect(page.get_by_text("Sales")).to_be_visible()
        expect(page.get_by_text("Complete your profile")).not_to_be_visible()
    finally:
        conn.close()


def test_create_order_and_upload_document_as_user(page: Page, app_server):
    """
    E2E test as user1: create an order in 'initial' state and upload a document.
    Verifies the full document upload flow works end-to-end from the browser.
    """
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        users = json.load(f)["users"]
    user1 = next(u for u in users if "user" in u["roles"])

    page.set_default_timeout(10000)
    page.goto(app_server + "/#/admin")
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
    page.wait_for_url("**#/admin/order/create**")

    # Fill the order form (total_amount is rollup read-only; customer is copy_logged_on_insert — auto-set)
    page.locator('input[name="order_date"]').fill("2024-01-15")
    page.locator('input[name="shipping_address_street"]').fill("_E2E Test Order Address")
    city = page.get_by_role("combobox", name="shipping address city")
    city.click()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")

    page.get_by_label("Save").click()
    # Wait for redirect to the edit page (URL contains a numeric order ID)
    page.wait_for_url(lambda url: bool(__import__('re').search(r'#/admin/order/\d+', url)), timeout=10000)
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


def _login_admin(page: Page, app_server):
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        admin_user = next(u for u in json.load(f)["users"] if "admin" in u["roles"])
    page.set_default_timeout(10000)
    page.goto(app_server + "/#/admin")
    page.wait_for_timeout(2000)
    page.locator('input[name="email"]').fill(admin_user["email"])
    page.locator('input[name="password"]').fill(admin_user["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Catalog")).to_be_visible()


def test_csv_export_import_roundtrip(page: Page, app_server, tmp_path):
    """
    CSV export/import round trip on products, browser only:
    export the product list (including the datasheet document column), assert the
    CSV carries id_presentation keys, m:n categories and base64 documents; then
    import a CSV that updates the seeded product and inserts a new one (with an
    m:n link and a document), confirm the "1 inserts, 1 updates" summary, and
    verify the result in the list and the database.
    """
    import csv
    import io
    import uuid

    _login_admin(page, app_server)
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    page.wait_for_url("**#/admin/product**")

    # -- Export with the datasheet document column included
    page.get_by_role("button", name="Export").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Export product to CSV")).to_be_visible()
    dialog.get_by_role("checkbox", name="datasheet").check()
    with page.expect_download(timeout=30000) as download_info:
        dialog.get_by_role("button", name="Export").click()
    csv_text = open(download_info.value.path(), encoding="utf-8").read()

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    headers = rows[0].keys()
    for col in ("id_presentation", "name", "sku", "categories",
                "doc:datasheet:filename", "doc:datasheet:content"):
        assert col in headers, f"Missing CSV column {col}. Headers: {list(headers)}"
    assert "id" not in headers, "The numeric id must never be exported"

    seeded = next(r for r in rows if r["sku"] == "SEED-KBD-001")
    assert seeded["id_presentation"] == "Seeded Keyboard"
    assert "Seeded Accessories" in seeded["categories"], \
        "m:n cells must carry the target id_presentation"
    # Exact category key as exported (recursive presentations may carry a path prefix)
    category_key = next(t for t in seeded["categories"].split("\n") if "Seeded Accessories" in t)
    assert seeded["doc:datasheet:filename"] == "seeded-keyboard.txt"
    assert "SW5pdGlhbCBwcm9kdWN0IGRhdGFzaGVldAo=" in seeded["doc:datasheet:content"], \
        "document content must be exported as base64"
    page.get_by_role("dialog").get_by_role("button", name="Close").click()

    # -- Build an import CSV: update the seeded product + insert a new one
    unique = uuid.uuid4().hex[:8]
    new_name = f"_CSV Import Product {unique}"
    new_description = f"_csv_e2e_updated_{unique}"
    import_file = tmp_path / "product_import.csv"
    with open(import_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id_presentation", "name", "description", "price",
                         "stock_quantity", "sku", "status", "categories",
                         "doc:datasheet:filename", "doc:datasheet:content"])
        writer.writerow(["Seeded Keyboard", "Seeded Keyboard", new_description,
                         "49.99", "25", "SEED-KBD-001", "published",
                         category_key, "", ""])
        # The m:n token is padded with spaces: import must match it against the
        # target id_presentation both verbatim and trimmed.
        writer.writerow(["", new_name, "created by CSV import", "10.50", "5",
                         f"CSV-E2E-{unique}", "draft", f"  {category_key}  ",
                         "imported-datasheet.txt",
                         "data:text/plain;base64,SW5pdGlhbCBwcm9kdWN0IGRhdGFzaGVldAo="])

    # -- Import: pick file, confirm the summary, expect success
    page.get_by_role("button", name="Import").click()
    dialog = page.get_by_role("dialog")
    dialog.locator('input[type="file"]').set_input_files(import_file)
    expect(dialog.get_by_text("1 inserts, 1 updates")).to_be_visible(timeout=15000)
    dialog.get_by_role("button", name="Confirm").click()
    expect(dialog.get_by_text("2 of 2 rows imported successfully")).to_be_visible(timeout=30000)
    dialog.get_by_role("button", name="Close").click()

    # -- The inserted product shows up in the list (sorted by name, "_" sorts first)
    page.get_by_role("button", name="Name").click()
    expect(page.get_by_role("cell", name=new_name).first).to_be_visible(timeout=10000)

    # -- DB check: update applied, m:n link and document created for the new product
    import psycopg2
    from dotenv import dotenv_values
    db_url = dotenv_values("test-app/backend/.env").get("DB_URL")
    assert db_url, "DB_URL not found in test-app/backend/.env"
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "description" FROM "product" WHERE "sku" = %s;', ("SEED-KBD-001",))
            assert cur.fetchone()[0] == new_description, "CSV update was not applied"
            cur.execute('SELECT "id" FROM "product" WHERE "name" = %s;', (new_name,))
            new_id = cur.fetchone()[0]
            cur.execute(
                'SELECT COUNT(*) FROM "category_product" cp JOIN "category" c '
                'ON c."id" = cp."category_id" '
                'WHERE cp."product_id" = %s AND c."name" = %s;',
                (new_id, "Seeded Accessories"))
            assert cur.fetchone()[0] == 1, "m:n link was not created on import"
            cur.execute(
                'SELECT "storage_path" FROM "product_document" '
                'WHERE "product_id" = %s AND "tag" = %s AND "is_current";',
                (new_id, "datasheet"))
            doc = cur.fetchone()
            assert doc and doc[0].endswith("imported-datasheet.txt"), \
                "document was not uploaded on import"
    finally:
        conn.close()


def test_csv_import_reports_all_errors(page: Page, app_server, tmp_path):
    """
    Importing a CSV with an unknown column, an unresolvable m:n value and a
    non-existent update key must report every problem with its record number
    and import nothing (there is no Confirm step on errors).
    """
    import csv

    _login_admin(page, app_server)
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    page.wait_for_url("**#/admin/product**")

    bad_file = tmp_path / "product_bad.csv"
    with open(bad_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id_presentation", "name", "price", "stock_quantity",
                         "sku", "status", "categories", "bogus_column"])
        writer.writerow(["___no_such_product___", "X", "1", "1", "BAD-1",
                         "published", "", ""])
        writer.writerow(["", "_Bad Import", "1", "1", "BAD-2", "published",
                         "___no_such_category___", ""])

    page.get_by_role("button", name="Import").click()
    dialog = page.get_by_role("dialog")
    dialog.locator('input[type="file"]').set_input_files(bad_file)

    expect(dialog.get_by_text("nothing was imported")).to_be_visible(timeout=15000)
    expect(dialog.get_by_text("unknown column")).to_be_visible()
    expect(dialog.get_by_text('"___no_such_product___" not found — cannot update')).to_be_visible()
    expect(dialog.get_by_text('category "___no_such_category___" not found')).to_be_visible()
    expect(dialog.get_by_role("button", name="Confirm")).not_to_be_visible()
    dialog.get_by_role("button", name="Close").click()


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
        f"http://localhost:{_FRONTEND_PORT}/**",
        lambda route: route.continue_(url=route.request.url.replace(f"localhost:{_FRONTEND_PORT}", f"localhost:{test_port}"))
    )

    # -- 1. Ensure we land on the login page.
    # The previous test may have left the user logged in; if so, log out via the
    # user menu so the session is clean before the forgot-password flow starts.
    page.goto(app_server + "/#/admin")
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
        page.wait_for_url("**#/admin/product**")
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
        api_url = os.getenv("SUPABASE_URL")
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
