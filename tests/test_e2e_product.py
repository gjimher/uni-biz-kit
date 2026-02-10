import pytest
import os
from playwright.sync_api import Page, expect
from xprocess import ProcessStarter

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
        
        frontend_dir = os.path.abspath("test-ecommerce-app/frontend")
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
    page.set_default_timeout(5000)
    print("creating product")
    # 1. Open the app
    page.goto(app_server)
    
    # 2. Go to Products
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