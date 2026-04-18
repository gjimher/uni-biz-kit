import pytest
import os
from smtp_mock import MockSMTPHandler, SMTP_PORT


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="run slow tests")


@pytest.fixture(scope="module")
def smtp_server():
    """Start an in-process SMTP mock on port 3010 for the duration of the module."""
    try:
        from aiosmtpd.controller import Controller
        controller = Controller(MockSMTPHandler(), hostname="0.0.0.0", port=SMTP_PORT)
        controller.start()
        yield controller
        controller.stop()
    except ImportError:
        pytest.skip("aiosmtpd not installed — run: pip install aiosmtpd")

def pytest_collection_modifyitems(config, items):
    """Enforce test file execution order:
    1. test_app_backend   — resets DB, seeds users (must run first)
    2. test_app_frontend  — checks generated frontend files
    3. test_app_api_auth  — API integration tests (needs seeded DB)
    4. test_app_e2e       — browser E2E tests (needs running app + seeded DB)
    """
    FILE_ORDER = [
        "test_app_backend",
        "test_app_frontend",
        "test_app_api_auth",
        "test_app_e2e",
    ]

    def file_rank(item):
        name = os.path.basename(str(item.fspath)).replace(".py", "")
        try:
            return FILE_ORDER.index(name)
        except ValueError:
            return len(FILE_ORDER)  # unknown files go last

    items.sort(key=file_rank)
