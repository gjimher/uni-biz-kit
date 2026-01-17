"""
Frontend Integration Test for Ecommerce App Generation

This test generates a complete ecommerce application frontend and compiles it.
"""

import pytest
import os
import sys
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from unibizkit.cli import CLI


class TestEcommerceFrontend:
    """Frontend integration tests for ecommerce app generation."""
    
    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_generate_ecommerce_frontend_and_compile(self):
        """Test generating a complete ecommerce app frontend and compiling it.
        
        This integration test:
        1. Generates a complete ecommerce application from schema
        2. Compiles the React frontend using npm
        3. Verifies the build is successful
        
        Note: This test may take several minutes to run.
        """
        cli = CLI()
        
        # Use the ecommerce schema from examples
        schema_path = Path('examples/ecommerce_schema.json')
        
        if not schema_path.exists():
            pytest.skip("Ecommerce schema not found")
        
        # Test directory (will be preserved between runs)
        test_output_dir = 'test-ecommerce-app'
        
        # Clean up only specific parts at the beginning of the test
        output_dir = Path(test_output_dir)
        
        # Remove SQL files and frontend/src if they exist from previous runs
        if output_dir.exists():
            # Remove SQL files
            for sql_file in output_dir.glob('*.sql'):
                sql_file.unlink()
            
            # Remove frontend/src directory to force regeneration
            frontend_src = output_dir / 'frontend' / 'src'
            if frontend_src.exists():
                shutil.rmtree(frontend_src)
        
        print("Executing unibizkit: generating a complete ecommerce application from schema")
        with patch('sys.argv', ['unibizkit', 'generate', str(schema_path), '--output-dir', test_output_dir]):
            # Should not raise an exception
            cli.run()
        
        # Check that output directory was created
        assert output_dir.exists()
        
        # Check that SQL files were generated
        assert (output_dir / 'supabase_schema.sql').exists()
        assert (output_dir / 'supabase_sample_data.sql').exists()
        
        # Check that frontend was generated
        frontend_dir = output_dir / 'frontend'
        assert frontend_dir.exists()
        assert (frontend_dir / 'package.json').exists()
        assert (frontend_dir / 'src' / 'App.js').exists()
        
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
            print("Building frontend: executing 'npm run build'")
            build_result = subprocess.run(
                ['npm', 'run', 'build'],
                stdout=sys.stdout, 
                stderr=sys.stderr, 
                timeout=600  # 10 minutes timeout
            )
            assert build_result.returncode == 0, f"Build failed with {build_result=}"
            
            # Check that build directory was created
            build_dir = Path("build")
            assert build_dir.exists()
            assert (build_dir / 'index.html').exists()
            assert (build_dir / 'static').exists()
            
            print("✓ Ecommerce frontend generated and compiled successfully!")
            
        finally:
            os.chdir(original_cwd)