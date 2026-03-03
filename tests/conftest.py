import pytest
import os

def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="run slow tests")

def pytest_collection_modifyitems(config, items):
    """Move tests containing 'e2e' to the end."""
    e2e_tests = []
    other_tests = []
    
    for item in items:
        # Check if the filename contains 'e2e'
        filename = os.path.basename(str(item.fspath))
        if "e2e" in filename:
            e2e_tests.append(item)
        else:
            other_tests.append(item)
    
    # Move e2e tests to the end.
    items[:] = other_tests + e2e_tests
