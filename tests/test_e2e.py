"""
Browser E2E Tests (Playwright)

All tests in this file require a running frontend server (--slow flag).
They interact exclusively through the browser — no direct API calls.
"""

import pytest
import os
import time
import json
from playwright.sync_api import Page, expect, TimeoutError as PlaywrightTimeoutError
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
        # Any non-admin seed user is a shopper (b2c names the role "buyer").
        user1 = next(u for u in json.load(f)["users"] if "admin" not in u["roles"])

    page.set_default_timeout(15000)
    page.goto(secondary_app_server + "/b2c/#/")

    # -- Sign in through the storefront page (not the admin login)
    page.get_by_role("link", name="Log in").click()
    page.get_by_label("Email").fill(user1["email"])
    page.get_by_label("Password").fill(user1["password"])
    page.get_by_role("button", name="Sign in").click()

    # First login of a seeded buyer: the post-login profile gate asks for the
    # mandatory "ask_after_login" names before continuing to the storefront.
    try:
        page.get_by_text("Complete your profile").wait_for(state="visible", timeout=4000)
        page.get_by_label("First name").fill("E2E")
        page.get_by_label("Last name").fill("Buyer")
        page.get_by_role("button", name="Save").click()
    except PlaywrightTimeoutError:
        pass  # profile already complete (gate skipped)

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


def test_presentation_customization_as_admin(page: Page, app_server, request):
    """Presentation customization overlays, admin side (production bundle):
    the role-less overlay applies (renamed price column, order list title),
    the user-scoped overlay must NOT leak (Test menu group present, delivered
    state offered), and — designer 'production' — the design toggle ships in
    the build as the per-user personalization editor.
    """
    if request.config.getoption("--variations"):
        pytest.skip("designer=off variation has no presentation customization runtime")
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        admin_user = next(u for u in json.load(f)["users"] if "admin" in u["roles"])

    page.set_default_timeout(10000)
    page.goto(app_server + "/#/admin")
    page.wait_for_timeout(2000)

    page.locator('input[name="email"]').fill(admin_user["email"])
    page.locator('input[name="password"]').fill(admin_user["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Catalog")).to_be_visible()

    # The user-scoped overlay (trimmed menu) must not apply to admins.
    expect(page.get_by_text("Test", exact=True)).to_be_visible()

    # designer 'production': the Design toggle ships in the build.
    expect(page.locator("header").get_by_text("Design")).to_be_visible()

    # Everyone-overlay: product price column renamed.
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    expect(page.get_by_role("button", name="Unit price")).to_be_visible()

    # Everyone-overlay: order list title renamed.
    page.get_by_text("Sales").click()
    page.get_by_role("menuitem", name="Orders").click()
    expect(page.get_by_text("Sales orders")).to_be_visible()

    # The user-scoped workflow_states hide must not apply to admins: the
    # create form's workflow selector still offers every state.
    page.get_by_label("Create").click()
    expect(page.get_by_role("radio", name="delivered")).to_be_visible()


def test_presentation_customization_as_user(page: Page, app_server, request):
    """Presentation customization overlays, user side (roles: ["user"]):
    trimmed menu without the Test group, customer.admin_field hidden in the
    edit form, delivered workflow state hidden in the selector — all on the
    same production bundle the admin test uses (runtime role scoping).
    """
    if request.config.getoption("--variations"):
        pytest.skip("designer=off variation has no presentation customization runtime")
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        user1 = next(u for u in json.load(f)["users"] if "user" in u["roles"])

    page.set_default_timeout(10000)
    page.goto(app_server + "/#/admin")
    page.wait_for_timeout(2000)

    page.locator('input[name="email"]').fill(user1["email"])
    page.locator('input[name="password"]').fill(user1["password"])
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Sales")).to_be_visible()

    # Menu replaced for users: the Test group is gone.
    expect(page.get_by_text("Test", exact=True)).to_have_count(0)

    # customer.admin_field is hidden in the user's forms (admins still see it).
    page.get_by_text("Sales").click()
    page.get_by_role("menuitem", name="Customers").click()
    page.locator("tbody tr").first.click()
    page.locator('input[name="phone"]').wait_for(state="visible")
    expect(page.locator('input[name="admin_field"]')).to_have_count(0)

    # forms.customer.move puts email first for users (runtime form reorder).
    expect(page.locator("form input:not([type=hidden])").first).to_have_attribute("name", "email")

    # delivered is hidden for users in the workflow selector (create form:
    # no record, so no current-state exception applies).
    page.get_by_text("Sales").click()
    page.get_by_role("menuitem", name="Orders").click()
    page.get_by_label("Create").click()
    expect(page.get_by_role("radio", name="sent")).to_be_visible()
    expect(page.get_by_role("radio", name="delivered")).to_have_count(0)


def test_personal_designer_end_user(page: Page, app_server, request):
    """designer 'production' per-user personalization on the production bundle:
    a user edits and saves their own design (stored in the _design table), it
    persists across logins, it never leaks to other users, and the
    designer_admin_role reviews it through the Customization menu.
    """
    if request.config.getoption("--variations"):
        pytest.skip("designer=off variation has no personal designer")
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        users = json.load(f)["users"]
    user1 = next(u for u in users if u["email"].startswith("user1"))
    admin_user = next(u for u in users if "admin" in u["roles"])

    page.set_default_timeout(10000)

    def login(user):
        page.goto(app_server + "/#/admin")
        page.wait_for_timeout(2000)
        user_menu = page.locator('header button[aria-label="Profile"]')
        if user_menu.is_visible():
            # Logging out lands on the public portal page; go back to the
            # admin entry to reach the sign-in form.
            user_menu.click()
            page.get_by_role("menuitem", name="Logout").click()
            page.wait_for_timeout(1000)
            page.goto(app_server + "/#/admin")
            page.wait_for_timeout(2000)
        page.locator('input[name="email"]').fill(user["email"])
        page.locator('input[name="password"]').fill(user["password"])
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_text("Sales")).to_be_visible()

    def reset_personalization():
        # Idempotent cleanup: deleting the (possibly absent) _design row and
        # reloading leaves this user on the application defaults.
        page.locator("header").get_by_text("Design", exact=True).click()
        expect(page.locator("header").get_by_text("My design")).to_be_visible()
        page.locator("header").get_by_text("My design").click()
        page.get_by_role("button", name="Reset personalization").click()
        page.wait_for_timeout(2500)

    # -- user1 personalizes: rename the product.name field label.
    login(user1)
    reset_personalization()
    page.locator("header").get_by_text("Design", exact=True).click()
    expect(page.locator("header").get_by_text("My design")).to_be_visible()
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    page.locator("tbody tr").first.click()
    page.get_by_label("Customize field product name").click()
    page.get_by_label("Label override").fill("Nombre propio")
    page.get_by_role("button", name="Apply to draft").click()
    expect(page.get_by_label("Nombre propio")).to_be_visible()

    # -- save to the _design table and verify it applies after the reload.
    page.locator("header").get_by_text("My design").click()
    page.get_by_role("button", name="Save my design").click()
    page.wait_for_timeout(3000)
    expect(page.get_by_label("Nombre propio")).to_be_visible()

    # -- the personalization is user1's only: another user sees the default label.
    login(admin_user)
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    page.locator("tbody tr").first.click()
    page.locator('input[name="name"]').wait_for(state="visible")
    expect(page.get_by_label("Nombre propio")).to_have_count(0)

    # -- the reviewer role sees every personalization in Customization/Designer.
    page.get_by_text("Customization").click()
    page.get_by_role("menuitem", name="Designer").click()
    expect(page.get_by_role("cell", name=user1["email"])).to_be_visible()

    # -- cleanup: user1 removes the personalization (keeps reruns deterministic).
    login(user1)
    reset_personalization()
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    page.locator("tbody tr").first.click()
    page.locator('input[name="name"]').wait_for(state="visible")
    expect(page.get_by_label("Nombre propio")).to_have_count(0)


def test_profile_completion_dialog_asks_for_missing_fields(page: Page, app_server):
    """
    E2E test of the post-login profile gate: customer.first_name/last_name are
    required "ask_after_login", so a user whose profile misses them is asked
    for them right after login — the sign-in page routes to /complete-profile
    before continuing to /admin (the blocking dialog remains as backstop for
    sessions established without the sign-in page, e.g. SSO). Filling the form
    saves the values and lets the admin UI through; the gate must not reappear
    on reload.

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
    page.locator('input[name="order_date"]').fill("2024-01-15T12:00")
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
    7. Restore the original password via the /change-password presentation page
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

        # -- 7. Restore original password via the /change-password page.
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
        # "Change Password" navigates to the customizable presentation page.
        page.get_by_role("link", name="Change Password").click()
        page.wait_for_url("**#/change-password**")
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


def test_generated_auth_pages(page: Page, app_server):
    """
    E2E of the generated default presentation auth pages (react-admin-free):
    0. a protected page without a session bounces to the app's own sign-in
    1. /#/signin shows the lib error inline on bad credentials
    2. and redirects to the home page on success
    3. /#/change-password rejects a mismatched confirmation inline
    """
    with open(os.path.abspath("test-app/security_extended.json")) as f:
        user1 = next(u for u in json.load(f)["users"] if "user" in u["roles"])

    page.set_default_timeout(10000)

    # -- 0. authenticated_pages guard: a signed-out visit to a priv page lands
    # on the sign-in page (which links the register flow).
    page.goto(app_server + "/#/priv/example-data")
    page.wait_for_url("**#/signin**")
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    expect(page.get_by_role("link", name="Create an account")).to_be_visible()

    # Fresh navigation so the post-login redirect goes home, not to the priv page.
    page.goto(app_server + "/#/signin")

    # -- 1. Wrong password: the lib error must surface inline in the form.
    page.get_by_label("Email").fill(user1["email"])
    page.get_by_label("Password").fill("wrong-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("alert")).to_contain_text("Invalid login credentials")

    # -- 2. Right password: the page redirects home once the session appears
    # (completing the profile gate first if user1's names are still empty).
    page.get_by_label("Password").fill(user1["password"])
    page.get_by_role("button", name="Sign in").click()
    try:
        page.get_by_text("Complete your profile").wait_for(state="visible", timeout=3000)
        page.get_by_label("First name").fill("Gate")
        page.get_by_label("Last name").fill("Signin")
        page.get_by_role("button", name="Save").click()
    except PlaywrightTimeoutError:
        pass  # profile already complete (gate skipped)
    expect(page.get_by_text("Welcome to the management portal")).to_be_visible()

    # -- 3. Change-password page: mismatched confirmation is rejected inline
    # (before any credential is touched).
    page.goto(app_server + "/#/change-password")
    page.get_by_label("Current Password").fill(user1["password"])
    page.get_by_label("New Password", exact=True).fill("newpassword123")
    page.get_by_label("Confirm New Password").fill("different123")
    page.get_by_role("button", name="Update Password").click()
    expect(page.get_by_role("alert")).to_contain_text("New passwords do not match")


def test_auth_errors_are_readable(page: Page, app_server):
    """
    Auth backend failures must surface as a human-readable message. supabase-js
    turns gateway timeouts/5xx into an error whose message is literally "{}"
    (seen in prod when the SMTP prerequisite was missing and signup returned a
    Kong 504); the lib must normalize it before pages render it.
    """
    page.route("**/auth/v1/signup**", lambda route: route.fulfill(
        status=504, content_type="application/json", body="{}",
    ))
    page.set_default_timeout(15000)
    page.goto(app_server + "/#/register")
    page.get_by_label("Email").fill("gateway-down@test.com")
    page.get_by_label("Password", exact=True).fill("password123")
    page.get_by_label("Confirm Password").fill("password123")
    page.get_by_role("button", name="Register").click()

    # supabase-js retries retryable 5xx a few times before giving up.
    alert = page.get_by_role("alert")
    expect(alert).to_be_visible(timeout=15000)
    assert alert.inner_text().strip() != "{}", "Auth errors must not render as raw '{}'"
    expect(alert).to_contain_text("try again")


def test_register_confirmation_lands_on_profile_gate(page: Page, app_server, smtp_server):
    """
    A session established WITHOUT passing through the sign-in page (here: the
    registration confirmation link; SSO is the other case) must still hit the
    profile-completion gate — the presentation router redirects to
    /complete-profile until the mandatory "ask_after_login" fields are filled.
    """
    import uuid
    email = f"e2e_gate_{uuid.uuid4().hex[:8]}@test.com"
    password = "RegisterGate123!"

    # Supabase site_url points at the dev frontend port; rewrite to this server.
    test_port = app_server.split(":")[-1].rstrip("/")
    page.route(
        f"http://localhost:{_FRONTEND_PORT}/**",
        lambda route: route.continue_(url=route.request.url.replace(f"localhost:{_FRONTEND_PORT}", f"localhost:{test_port}"))
    )

    with _smtp_lock:
        _smtp_emails.clear()

    # -- 1. Register through the generated page
    page.set_default_timeout(10000)
    page.goto(app_server + "/#/register")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_label("Confirm Password").fill(password)
    page.get_by_role("button", name="Register").click()
    expect(page.get_by_text("Registration successful!")).to_be_visible()

    try:
        # -- 2. Wait for the confirmation email from the SMTP mock
        deadline = time.time() + 10
        email_received = None
        while time.time() < deadline:
            with _smtp_lock:
                matching = [e for e in _smtp_emails if email in e["rcpt_tos"]]
            if matching:
                email_received = matching[-1]
                break
            time.sleep(0.5)
        assert email_received, "Confirmation email not received via the SMTP mock"
        links = [l for l in _extract_links(email_received["content"]) if "verify" in l or "confirm" in l]
        assert links, f"No confirmation link found in the email: {_extract_links(email_received['content'])}"

        # -- 3. The link logs the user in directly — the gate must intercept
        # before they browse on, and completing it lands them on the home page.
        page.goto(links[0])
        expect(page.get_by_text("Complete your profile")).to_be_visible(timeout=15000)
        page.get_by_label("First name").fill("Confirmed")
        page.get_by_label("Last name").fill("ByEmail")
        page.get_by_role("button", name="Save").click()
        expect(page.get_by_text("Welcome to the management portal")).to_be_visible()
    finally:
        # Remove the throwaway account so reruns don't accumulate users.
        import requests
        from dotenv import load_dotenv
        load_dotenv("test-app/backend/.env")
        api_url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if api_url and service_role_key:
            headers = {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}
            users_resp = requests.get(f"{api_url}/auth/v1/admin/users", headers=headers)
            if users_resp.status_code == 200:
                target = next((u for u in users_resp.json().get("users", []) if u["email"] == email), None)
                if target:
                    requests.delete(f"{api_url}/auth/v1/admin/users/{target['id']}", headers=headers)


# ---------------------------------------------------------------------------
# Design mode save endpoint (Vite dev server only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dev_server(xprocess, request):
    """Vite dev server for endpoint contract tests (no browser rendering)."""
    if not request.config.getoption("--slow"):
        pytest.skip("need --slow option to run")

    frontend_dir = os.path.abspath("test-app/frontend")

    class Starter(ProcessStarter):
        pattern = "Local:"
        env = os.environ.copy()
        args = ["npm", "--prefix", frontend_dir, "run", "start", "--", "--port", str(_FRONTEND_PORT)]
        cwd = frontend_dir
        timeout = 60

    try:
        xprocess.getinfo("dev_server_pure").terminate()
    except Exception:
        pass

    xprocess.ensure("dev_server_pure", Starter)
    yield f"http://localhost:{_FRONTEND_PORT}"
    xprocess.getinfo("dev_server_pure").terminate()


def test_presentation_custom_dev_endpoint(dev_server, request):
    """Contract of the design-mode save endpoint (/__ubk/presentation-custom,
    dev server only): GET lists the model's overlay files with parsed content,
    PUT round-trips a new overlay into models/<app>/, and file names outside
    the presentation-custom-NN.jsonc whitelist or unknown sections are
    rejected with 400 without writing anything.
    """
    if request.config.getoption("--variations"):
        pytest.skip("designer=off variation has no customization endpoint")
    import urllib.request
    import urllib.error

    endpoint = dev_server + "/__ubk/presentation-custom"

    def get():
        with urllib.request.urlopen(endpoint, timeout=15) as resp:
            return json.loads(resp.read())

    def put(body):
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request, timeout=15)

    data = get()
    assert "presentation-custom-00.jsonc" in data["files"]
    assert any(
        overlay["file"] == "presentation-custom-10.jsonc" and overlay["roles"] == ["user"]
        for overlay in data["overlays"]
    )

    test_file = "presentation-custom-90.jsonc"
    model_path = os.path.abspath("models/test-app/" + test_file)
    content = json.dumps(
        {"description": "e2e roundtrip", "labels": {"titles": {"product": "Products (e2e)"}}},
        indent=2,
    )
    try:
        with put({"file": test_file, "content": content}) as resp:
            assert resp.status == 200
        assert os.path.exists(model_path)
        data = get()
        saved = next(overlay for overlay in data["overlays"] if overlay["file"] == test_file)
        assert saved["order"] == 90
        assert saved["labels"]["titles"]["product"] == "Products (e2e)"

        replacement = json.dumps({"description": "confirmed replacement"}, indent=2)
        try:
            put({"file": test_file, "content": replacement})
            assert False, "an unconfirmed overwrite must be rejected"
        except urllib.error.HTTPError as error:
            assert error.code == 409
        assert json.loads(Path(model_path).read_text())["description"] == "e2e roundtrip"
        with put({"file": test_file, "content": replacement, "overwrite": True}) as resp:
            assert resp.status == 200
        assert json.loads(Path(model_path).read_text())["description"] == "confirmed replacement"

        for bad in (
            {"file": "../evil.jsonc", "content": "{}"},
            {"file": "presentation-custom-91.jsonc", "content": json.dumps({"typo_section": {}})},
        ):
            try:
                put(bad)
                assert False, f"expected HTTP 400 for {bad}"
            except urllib.error.HTTPError as error:
                assert error.code == 400
        assert not os.path.exists(os.path.abspath("models/test-app/presentation-custom-91.jsonc"))
    finally:
        if os.path.exists(model_path):
            os.remove(model_path)
