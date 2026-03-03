import pytest
import os
import time
import json
import urllib.request
from playwright.sync_api import Page, expect
from xprocess import ProcessStarter
from dotenv import load_dotenv

def test_auth_api_login():
    """
    Verify that generated users can login via Supabase Auth API.
    This tests the API directly, similar to how the frontend does it.
    """
    backend_dir = os.path.abspath("test-app/backend")
    frontend_dir = os.path.abspath("test-app/frontend")
    
    security_extended_file = os.path.abspath("test-app/security_extended.json")
    assert os.path.exists(security_extended_file), "security_extended.json not found"
    
    with open(security_extended_file, 'r') as f:
        security_data = json.load(f)
        auth_users = security_data["users"]
    
    load_dotenv(os.path.join(frontend_dir, ".env"))
    api_url = os.getenv("REACT_APP_SUPABASE_URL")
    anon_key = os.getenv("REACT_APP_SUPABASE_KEY")
    
    assert api_url, "REACT_APP_SUPABASE_URL not found in frontend .env"
    assert anon_key, "REACT_APP_SUPABASE_KEY not found in frontend .env"

    for user in auth_users:
        email = user["email"]
        password = user["password"]
        print(f"Testing login for: {email}")
        
        # Supabase Auth API login
        url = f"{api_url}/auth/v1/token?grant_type=password"
        data = json.dumps({
            "email": email,
            "password": password
        }).encode('utf-8')
        
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={
                'apikey': anon_key,
                'Content-Type': 'application/json'
            },
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                assert response.status == 200
                res_body = json.loads(response.read().decode('utf-8'))
                access_token = res_body["access_token"]
                assert access_token
                assert res_body["user"]["email"] == email
                print(f"  Login successful for {email}")
                
                # Check DB Insert access
                insert_url = f"{api_url}/rest/v1/product"
                insert_data = json.dumps({
                    "name": f"Test product by {email}",
                    "price": 10.00,
                    "stock_quantity": 5,
                    "sku": f"TEST-SKU-{email.split('@')[0]}-{int(time.time())}",
                    "status": "draft"
                }).encode('utf-8')                
                insert_req = urllib.request.Request(
                    insert_url,
                    data=insert_data,
                    headers={
                        'apikey': anon_key,
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json',
                        'Prefer': 'return=minimal'
                    },
                    method='POST'
                )
                
                role = "admin" if "admin" in user["roles"] else "user"
                
                try:
                    with urllib.request.urlopen(insert_req) as insert_response:
                        if role == "user":
                            pytest.fail(f"User {email} (role: {role}) was able to insert into product table but should not be allowed.")
                        else:
                            print(f"  Insert successful for {email} (role: {role})")
                except urllib.error.HTTPError as e:
                    if role == "admin":
                        pytest.fail(f"Admin {email} failed to insert into product table: {e.code} {e.read().decode('utf-8')}")
                    else:
                        print(f"  Insert correctly blocked for {email} (role: {role}): {e.code}")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            pytest.fail(f"Login failed for {email}: {e.code} {error_body}")

@pytest.fixture(scope="module")
def app_server(xprocess, request):
    if not request.config.getoption("--slow"):
        pytest.skip("need --slow option to run")

    class Starter(ProcessStarter):
        pattern = "Local:"
        
        # Args for starting the server
        env = os.environ.copy()
        env["PORT"] = "3005"
        env["BROWSER"] = "none"
        
        frontend_dir = os.path.abspath("test-app/frontend")
        args = ["npm", "start", "--prefix", frontend_dir]
        cwd = frontend_dir
        timeout = 15
        print("starting web server in port 3005: npm start")

    xprocess.ensure("app_server_pure", Starter)
    yield "http://localhost:3005"
    xprocess.getinfo("app_server_pure").terminate()

def test_create_product_as_user(page: Page, app_server):
    """
    Pure E2E test: No mocks, no interceptions.
    Acts as a real user creating a product.
    """
    security_extended_file = os.path.abspath("test-app/security_extended.json")
    with open(security_extended_file, 'r') as f:
        security_data = json.load(f)
        admin_user = next(u for u in security_data["users"] if "admin" in u["roles"])

    page.set_default_timeout(10000)
    print("logging in and creating product")
    # 1. Open the app
    page.goto(app_server)

    # Login
    page.locator('input[name="username"]').fill(admin_user["email"])
    page.locator('input[name="password"]').fill(admin_user["password"])
    page.get_by_role("button", name="Sign in").click()
    
    # Wait for login to complete by checking for a menu item
    expect(page.get_by_text("Catalog")).to_be_visible()
    
    # 2. Go to Products
    # Expand Catalog menu first
    page.get_by_text("Catalog").click()
    page.get_by_role("menuitem", name="Products").click()
    
    # 3. Open Creation Form
    page.get_by_label("Create").click()
    
    # 4. Fill Product Details
    page.get_by_label("Name").fill("_User Journey Product")
    page.get_by_label("Price").fill("49.99")
    page.get_by_label("Stock quantity").fill("100")
    page.get_by_label("Sku").fill("PURE-E2E-001")
    
    # 5. Select Status
    page.get_by_label("Status").click()
    # We use 'published' as a valid enum value from the schema
    page.get_by_role("option", name="published").click()
    
    # 6. Save (Categories are now in the Relations tab on Edit page)
    page.get_by_label("Save").click()
    
    # Wait for success notification and redirection
    page.wait_for_timeout(1000)
    
    # 7. Verify it exists in the list
    # The user specifically asked to check it in the list
    page.get_by_role("menuitem", name="Products").click()
    
    # Sort by Name to ensure it's on the first page
    page.get_by_role("button", name="Name").click()
    # Wait for sort to apply
    page.wait_for_timeout(500)

    product_cell = page.get_by_role("cell", name="_User Journey Product").first
    expect(product_cell).to_be_visible()
    expect(page.get_by_role("cell", name="PURE-E2E-001").first).to_be_visible()

    # 8. Verify Relations Tab
    # Open the product to check the Relations tab
    product_cell.click()
    page.get_by_role("tab", name="Relations").click()
    expect(page.get_by_label("Categories")).to_be_visible()
