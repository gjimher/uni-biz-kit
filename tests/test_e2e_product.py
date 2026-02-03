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
        timeout = 120
        print("starting web server in port 3005: npm start")

    xprocess.ensure("app_server_pure", Starter)
    yield "http://localhost:3005"
    xprocess.getinfo("app_server_pure").terminate()

def test_create_product_as_user(page: Page, app_server):
    """
    Pure E2E test: No mocks, no interceptions.
    Acts as a real user creating a product.
    """
    print("creating product")
    # 1. Open the app
    page.goto(app_server)
    
    # 2. Go to Products
    page.get_by_role("menuitem", name="Products").click()
    
    # 3. Open Creation Form
    page.get_by_label("Create").click()
    
    # 4. Fill Product Details
    page.get_by_label("Name").fill("User Journey Product")
    page.get_by_label("Price").fill("49.99")
    page.get_by_label("Stock quantity").fill("100")
    page.get_by_label("Sku").fill("PURE-E2E-001")
    
    # 5. Select Status
    page.get_by_label("Status").click()
    # We use 'published' as a valid enum value from the schema
    page.get_by_role("option", name="published").click()
    
    # 6. Select Category
    # We open the dropdown and pick the first available option from the seed
    page.get_by_label("Categories").click()
    # Wait for options to be visible
    category_option = page.get_by_role("option").first
    category_option.wait_for(state="visible")
    category_option.click()
    # Close dropdown (MUI Select multiple doesn't close on click)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    
    # 7. Save
    page.get_by_label("Save").click()
    
    # Wait for success notification and redirection
    page.wait_for_timeout(1000)
    
    # 8. Verify it exists in the list
    # The user specifically asked to check it in the list
    page.get_by_role("menuitem", name="Products").click()
    
    expect(page.get_by_role("cell", name="User Journey Product")).to_be_visible()
    expect(page.get_by_role("cell", name="PURE-E2E-001")).to_be_visible()