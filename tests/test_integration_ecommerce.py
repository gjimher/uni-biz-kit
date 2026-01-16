"""
Integration Test for Ecommerce App Generation and Compilation

This test generates a complete ecommerce application and compiles it to ensure
the generated code is valid and can be built successfully.
"""

import pytest
import tempfile
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch
from unibizkit.cli import CLI


class TestEcommerceIntegration:
    """Integration tests for ecommerce app generation."""
    
    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_generate_ecommerce_app_and_compile(self):
        """Test generating a complete ecommerce app and compiling it.
        
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
        
        # Try to compile the frontend (this will test if the generated code is valid)
        import subprocess
        
        # Change to frontend directory
        original_cwd = os.getcwd()
        os.chdir(frontend_dir)
        
        try:
            # Install dependencies (only if node_modules doesn't exist)
            node_modules = frontend_dir / 'node_modules'
            if not node_modules.exists():
                print("Installing npm dependencies...")
                install_result = subprocess.run(
                    ['npm', 'install', '--silent'],
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes timeout
                )
                
                # Always show stderr for debugging, even on success
                if install_result.stderr:
                    print(f"npm install stderr: {install_result.stderr}")
                
                # Also show stdout for debugging
                if install_result.stdout:
                    print(f"npm install stdout: {install_result.stdout}")
                
                # Check if npm install succeeded
                if install_result.returncode != 0:
                    assert False, f"npm install failed with return code {install_result.returncode}. stderr: {install_result.stderr}"
            
            # Try to build the project
            print("Building frontend...")
            build_result = subprocess.run(
                ['npm', 'run', 'build'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            # Always show stderr for debugging, even on success
            if build_result.stderr:
                print(f"Build stderr: {build_result.stderr}")
            
            # Also show stdout for debugging
            if build_result.stdout:
                print(f"Build stdout: {build_result.stdout}")
            
            # Check if build succeeded
            if build_result.returncode != 0:
                assert False, f"Build failed with return code {build_result.returncode}. stderr: {build_result.stderr}"
            
            # Check that build directory was created
            build_dir = Path("build")
            assert build_dir.exists()
            assert (build_dir / 'index.html').exists()
            assert (build_dir / 'static').exists()
            
            print("✓ Ecommerce app generated and compiled successfully!")
            
        finally:
            os.chdir(original_cwd)
            
