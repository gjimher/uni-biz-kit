import pytest
import os

def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="run slow tests")

def pytest_collection_modifyitems(config, items):
    """Move tests starting with test_e2e to the end."""
    e2e_tests = []
    other_tests = []
    
    for item in items:
        # Check if the filename starts with test_e2e
        filename = os.path.basename(str(item.fspath))
        if filename.startswith("test_e2e"):
            e2e_tests.append(item)
        else:
            other_tests.append(item)
    
    # If we are in slow mode and have e2e tests, skip frontend tests
    if config.getoption("--slow") and e2e_tests:
        skip_frontend = pytest.mark.skip(reason="Skipping frontend tests because e2e tests are running in slow mode")
        for item in other_tests:
            if "test_ecommerce_frontend.py" in str(item.fspath):
                item.add_marker(skip_frontend)
            
    items[:] = other_tests + e2e_tests
