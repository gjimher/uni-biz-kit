"""
Backend Integration Test for App App Generation

This test generates a complete app application backend and sets up the database.
"""

import pytest
import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch
from unibizkit.cli import CLI


def _run(cmd, timeout=600):
    """Run a command, capture output, print it in order, and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    return result


class TestAppBackend:
    """Backend integration tests for app app generation."""

    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_generate_app_backend_and_setup_database(self):
        """Test generating a complete app app backend and setting up the database.

        This integration test:
        1. Generates a complete app application from schema
        2. Sets up Supabase database with schema and sample data
        3. Verifies the database setup is successful

        Note: This test may take several minutes to run.
        """
        cli = CLI()

        # Use the app schema from models
        output_dir = Path('test-app').resolve()

        print("Executing uni-biz-kit: generating a complete app application from schema")
        with patch('sys.argv', ['uni-biz-kit', 'models/test-app', '--output-dir', str(output_dir)]):
            cli.run()

        assert output_dir.exists()

        backend_dir = output_dir / 'backend'
        original_cwd = os.getcwd()

        try:
            supabase_dir = backend_dir / 'supabase'
            if not supabase_dir.exists():
                print("Running dev-supabase-start.py...")
                create_script = output_dir / 'bin' / 'dev-supabase-start.py'
                result = _run([sys.executable, str(create_script)], timeout=600)
                assert result.returncode == 0, f"dev-supabase-start.py failed with code {result.returncode}"
            else:
                print("Supabase directory already exists, skipping initialization")

            print("Running dev-supabase-reset-schema-and-data.py...")
            reset_script = output_dir / 'bin' / 'dev-supabase-reset-schema-and-data.py'
            result = _run([sys.executable, str(reset_script), '--force'], timeout=120)
            assert result.returncode == 0, f"dev-supabase-reset-schema-and-data.py failed with code {result.returncode}"

        finally:
            os.chdir(original_cwd)
