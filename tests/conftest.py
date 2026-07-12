import pytest
import os
import sys
import subprocess
from pathlib import Path
from smtp_mock import MockSMTPHandler, SMTP_PORT
from unibizkit.schema_loader import _load_jsonc_file


# --- Optional secondary development environment (UBK_DEV_MODEL) ---------------
# When UBK_DEV_MODEL is set, a second app is generated alongside test-app and
# served on a +50 port offset. If it is unset, pytest only works with test-app.
SECONDARY_MODEL = os.environ.get("UBK_DEV_MODEL")
HAS_SECONDARY_MODEL = bool(SECONDARY_MODEL)

_ENV_NUM = int(os.environ.get("UBK_DEV_ENV_NUM", "0"))
PRIMARY_BASE = 3000 + 100 * _ENV_NUM
SECONDARY_BASE = PRIMARY_BASE + 50
SECONDARY_FRONTEND_PORT = SECONDARY_BASE + 0
SECONDARY_PREVIEW_PORT = SECONDARY_BASE + 1


def secondary_model_kind_error():
    if not HAS_SECONDARY_MODEL:
        return None
    model_dir = Path("models") / SECONDARY_MODEL
    deployment_path = model_dir / "deployment.jsonc"
    concepts_path = model_dir / "concepts.jsonc"
    if not deployment_path.exists() or concepts_path.exists():
        return None
    try:
        deployment = _load_jsonc_file(str(deployment_path))
    except Exception:
        return None
    if "proxy" not in deployment:
        return None
    return (
        f"UBK_DEV_MODEL={SECONDARY_MODEL} is a proxy model; "
        "UBK_DEV_MODEL must be a normal app model with concepts.jsonc."
    )


def assert_secondary_model_is_normal_app():
    error = secondary_model_kind_error()
    if error:
        pytest.fail(error)


def generate_secondary_model():
    """Generate the secondary model into ./<SECONDARY_MODEL> on the +50 port offset.

    Pytest computes and passes the exact base port. Run in a subprocess to keep the
    primary in-process generation and this secondary generation cleanly separated."""
    if not HAS_SECONDARY_MODEL:
        pytest.skip("UBK_DEV_MODEL is not set; secondary dev environment disabled")
    assert_secondary_model_is_normal_app()

    result = subprocess.run(
        [
            sys.executable, "-m", "unibizkit.cli",
            f"models/{SECONDARY_MODEL}", "--output-dir", SECONDARY_MODEL,
            "--dev-base-port", str(SECONDARY_BASE),
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
    parser.addoption(
        "--slow-prod", action="store_true",
        help="run destructive production deployment tests against ubk-prod",
    )


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
