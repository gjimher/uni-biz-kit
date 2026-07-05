"""
Frontend Integration Test for App App Generation

This test generates a complete app application frontend and compiles it.
"""

import pytest
import os
import sys
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from unibizkit.cli import CLI
from conftest import PRIMARY_BASE


class TestAppFrontend:
    """Frontend integration tests for app app generation."""
    
    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_generate_app_frontend_and_compile(self):
        """Test generating a complete app app frontend and compiling it.
        
        This integration test:
        1. Generates a complete app application from schema
        2. Compiles the React frontend using npm
        3. Verifies the build is successful
        
        Note: This test may take several minutes to run.
        """
        cli = CLI()
        
        # Use the app schema from models
        schema_path = Path('models/test-app/concepts.jsonc')
        output_dir = Path('test-app')
        
        print("Executing uni-biz-kit: generating a complete app application from schema")
        with patch('sys.argv', [
            'uni-biz-kit', 'models/test-app',
            '--output-dir', str(output_dir),
            '--dev-base-port', str(PRIMARY_BASE),
        ]):
            # Should not raise an exception
            cli.run()
        
        # Check that output directory was created
        assert output_dir.exists()
        dev_info_ports = (output_dir / 'bin' / 'dev-info-ports.py').read_text()
        assert f"BASE_PORT = {PRIMARY_BASE}" in dev_info_ports

        frontend_dir = output_dir / 'frontend'

        # The shared helper library for custom presentation pages must be generated.
        lib_dir = frontend_dir / 'src' / 'presentation' / 'lib'
        for module in ('auth.js', 'profile.js', 'payment.js', 'validations.js', 'format.js', 'workflow.js', 'storage.js', 'index.js'):
            assert (lib_dir / module).exists(), f"Missing generated presentation lib module: {module}"

        # Validation logic must be deduplicated: resources import it from the shared lib.
        address_resource = (frontend_dir / 'src' / 'resources' / 'address' / 'address.jsx').read_text()
        assert "from '../../presentation/lib/validations'" in address_resource, \
            "Validation resource should import shared logic from presentation/lib/validations"

        # Markdown fields must use the generated markdown editor component.
        product_resource = (frontend_dir / 'src' / 'resources' / 'product' / 'product.jsx').read_text()
        assert "from '../../components/markdown_input'" in product_resource, \
            "Resource with a markdown field should import the generated markdown component"
        assert '<MarkdownInput source="details"' in product_resource
        package_json = (frontend_dir / 'package.json').read_text()
        assert '"@uiw/react-md-editor"' in package_json, \
            "Markdown editor dependency should be added when the model uses markdown fields"

        # Change to frontend directory
        original_cwd = os.getcwd()
        
        try:
            os.chdir(frontend_dir)
            
            # Install dependencies (only if node_modules doesn't exist)
            node_modules = frontend_dir / 'node_modules'
            if not node_modules.exists():
                print("Installing npm dependencies: executing 'npm install --silent'")
                install_result = subprocess.run(
                    ['npm', 'install', '--silent'],
                    stdout=sys.stdout, 
                    stderr=sys.stderr, 
                    timeout=600  # 10 minutes timeout
                )
                assert install_result.returncode == 0, f"npm install failed with {install_result=}"
            
            # Try to build the project
            print("Checking generated js: executing 'npm run lint -- --max-warnings 0'")
            build_result = subprocess.run(
                ['npm', 'run', 'lint', '--', '--max-warnings', '0'], 
                stdout=sys.stdout, 
                stderr=sys.stderr, 
                timeout=600  # 10 minutes timeout
            )
            assert build_result.returncode == 0, f"Lint failed or warnings found. {build_result=}"
                        
            print("✓ App frontend generated and compiled successfully!")
            
        finally:
            os.chdir(original_cwd)

    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_secondary_frontend_builds(self):
        """Generate the second dev environment's frontend (UBK_DEV_MODEL) and build it.

        Mirrors the primary frontend test for the +50-offset secondary model: it
        proves a second app can be generated and produce a working production bundle.
        """
        from conftest import generate_secondary_model

        output_dir = generate_secondary_model()
        from conftest import SECONDARY_BASE
        dev_info_ports = (output_dir / 'bin' / 'dev-info-ports.py').read_text()
        assert f"BASE_PORT = {SECONDARY_BASE}" in dev_info_ports

        frontend_dir = output_dir / 'frontend'
        original_cwd = os.getcwd()

        try:
            os.chdir(frontend_dir)

            # Install dependencies only if missing (node_modules is preserved between runs).
            node_modules = frontend_dir / 'node_modules'
            if not node_modules.exists():
                print("Installing npm dependencies: executing 'npm install --silent'")
                install_result = subprocess.run(
                    ['npm', 'install', '--silent'],
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    timeout=600,
                )
                assert install_result.returncode == 0, f"npm install failed with {install_result=}"

            print("Building secondary frontend: executing 'npm run build -- --mode development'")
            build_result = subprocess.run(
                ['npm', 'run', 'build', '--', '--mode', 'development'],
                stdout=sys.stdout,
                stderr=sys.stderr,
                timeout=600,
            )
            assert build_result.returncode == 0, f"Secondary frontend build failed. {build_result=}"

            print("✓ Secondary frontend generated and built successfully!")
        finally:
            os.chdir(original_cwd)

    def test_filter_list_fields(self):
        """Test the logic for filtering list fields based on string modifiers."""
        from unibizkit.react_admin_generator import ReactAdminGenerator
        
        pool = ['id_presentation', 'a', 'b', 'c', 'd', 'e', '_private']
        
        # Test basic inclusion (puts at end)
        assert ReactAdminGenerator.filter_list_fields(pool, [], 'a, c') == ['a', 'c']
        
        # Test all (*)
        assert ReactAdminGenerator.filter_list_fields(pool, [], '*') == ['id_presentation', 'a', 'b', 'c', 'd', 'e', '_private']
        
        # Test default level 1 (exclude id_presentation and anything starting with _)
        assert ReactAdminGenerator.filter_list_fields(pool, [], '*, !id_presentation, !_*') == ['a', 'b', 'c', 'd', 'e']
        
        # Test prefix matching (xxx*)
        pool_extra = pool + ['ax', 'ay']
        assert ReactAdminGenerator.filter_list_fields(pool_extra, [], 'a*') == ['a', 'ax', 'ay']
        
        # Test prefix exclusion (!xxx*)
        assert ReactAdminGenerator.filter_list_fields(pool_extra, ['a', 'ax', 'ay', 'b'], '!a*') == ['b']
        
        # Test ordering [0] (move to front)
        assert ReactAdminGenerator.filter_list_fields(pool, ['a', 'b'], 'c[0]') == ['c', 'a', 'b']
        
        # Test ordering [-1] (move to end)
        assert ReactAdminGenerator.filter_list_fields(pool, ['a', 'b'], 'c[-1]') == ['a', 'b', 'c']
        
        # Test ordering [prev] (move after prev)
        assert ReactAdminGenerator.filter_list_fields(pool, ['a', 'b', 'c'], 'd[a]') == ['a', 'd', 'b', 'c']
        
        # Test cumulative levels
        # Level 1: Default general rules
        l1 = ReactAdminGenerator.filter_list_fields(pool, [], '*, !id_presentation, !_*') # ['a', 'b', 'c', 'd', 'e']
        assert l1 == ['a', 'b', 'c', 'd', 'e']
        
        # Level 2: App-wide override (e.g. move id_presentation to front)
        l2 = ReactAdminGenerator.filter_list_fields(pool, l1, 'id_presentation[0]') 
        assert l2 == ['id_presentation', 'a', 'b', 'c', 'd', 'e']
        
        # Level 3: Concept-specific override (e.g. remove c, move e to front)
        l3 = ReactAdminGenerator.filter_list_fields(pool, l2, '!c, e[0]')
        assert l3 == ['e', 'id_presentation', 'a', 'b', 'd']

    
