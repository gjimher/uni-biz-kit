import pytest
import os
import sys
import subprocess
from pathlib import Path
from smtp_mock import MockSMTPHandler, SMTP_PORT


# --- Secondary development environment (UBK_DEV_MODEL) ------------------------
# A second app is generated alongside test-app and served on a +50 port offset
# (base+50..99). The primary env uses base+0..49; see generators/dev_ports.py.
SECONDARY_MODEL = os.environ.get("UBK_DEV_MODEL") or "test-dummy-app"

_ENV_NUM = int(os.environ.get("UBK_DEV_ENV_NUM", "0"))
SECONDARY_BASE = 3000 + 100 * _ENV_NUM + 50
SECONDARY_FRONTEND_PORT = SECONDARY_BASE + 0
SECONDARY_PREVIEW_PORT = SECONDARY_BASE + 1


def generate_secondary_model():
    """Generate the secondary model into ./<SECONDARY_MODEL> on the +50 port offset.

    The CLI applies the +50 itself because the model name matches UBK_DEV_MODEL, so
    no extra environment variable is needed. Run in a subprocess to keep the primary
    in-process generation (offset 0) and this one (offset 50) cleanly separated."""
    result = subprocess.run(
        [
            sys.executable, "-m", "unibizkit.cli",
            f"models/{SECONDARY_MODEL}", "--output-dir", SECONDARY_MODEL,
        ],
        capture_output=True, text=True, timeout=600,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    assert result.returncode == 0, (
        f"Secondary model generation failed ({SECONDARY_MODEL}) with code {result.returncode}"
    )
    output_dir = Path(SECONDARY_MODEL).resolve()
    assert output_dir.exists(), f"Secondary output dir not created: {output_dir}"
    return output_dir


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
    1. test_backend   — resets DB, seeds users (must run first)
    2. test_frontend  — checks generated frontend files
    3. test_api_auth  — API integration tests (needs seeded DB)
    4. test_e2e       — browser E2E tests (needs running app + seeded DB)
    """
    FILE_ORDER = [
        "test_backend",
        "test_frontend",
        "test_api_auth",
        "test_e2e",
    ]

    def file_rank(item):
        name = os.path.basename(str(item.fspath)).replace(".py", "")
        try:
            return FILE_ORDER.index(name)
        except ValueError:
            return len(FILE_ORDER)  # unknown files go last

    items.sort(key=file_rank)
