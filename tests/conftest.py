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
    
    # Move tests starting with test_e2e to the end.
    items[:] = other_tests + e2e_tests
