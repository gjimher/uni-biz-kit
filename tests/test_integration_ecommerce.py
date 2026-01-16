"""
Integration Test for Ecommerce App Generation and Compilation

This test generates a complete ecommerce application and compiles it to ensure
the generated code is valid and can be built successfully.
"""

import pytest
import json
import os
import shutil
import time
import re
import subprocess
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
        
        # Change to frontend directory
        original_cwd = os.getcwd()
        
        try:
            os.chdir(output_dir)
            # Check if supabase directory exists, if not initialize it
            supabase_dir = Path('supabase')
            if not supabase_dir.exists():
                print("Initializing Supabase...")
                
                # Initialize supabase
                init_result = subprocess.run(
                    ['npx', '-y', 'supabase', 'init'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if init_result.returncode != 0:
                    print(f"Supabase init failed: {init_result.stderr}")
                    assert False, f"Supabase init failed with return code {init_result.returncode}"

                print("Changing Supabase ports from 54xxx to 55xxx in supabase/config.toml")
                config_path = Path("supabase/config.toml")
                text = config_path.read_text()
                text = re.sub(r"\b54(\d{3})\b", r"55\1", text)
                config_path.write_text(text)
                
                # Start supabase
                print("Starting Supabase...")
                start_result = subprocess.run(
                    ['npx', 'supabase', 'start'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if start_result.returncode != 0:
                    print(f"Supabase start failed: {start_result.stderr}")
                    assert False, f"Supabase start failed with return code {start_result.returncode}"
                
                # Wait a bit for supabase to be ready
                time.sleep(10)
                
                # Create .env file with supabase credentials
                print("Creating .env file...")
                env_content = ""
                try:
                    status_result = subprocess.run(
                        ['npx', 'supabase', 'status', '-o', 'json'],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if status_result.returncode == 0:
                        status_data = json.loads(status_result.stdout)
                        api_url = status_data.get('API_URL', '')
                        anon_key = status_data.get('ANON_KEY', '')
                        
                        env_content = f"REACT_APP_SUPABASE_URL={api_url}\nREACT_APP_SUPABASE_KEY={anon_key}\n"
                    else:
                        print(f"Could not get supabase status: {status_result.stderr}")
                except Exception as e:
                    print(f"Error creating .env file: {e}")
                
                # Write .env file
                with open('frontend/.env', 'w') as env_file:
                    env_file.write(env_content)
                
                # Change back to original directory
                os.chdir(original_cwd)
            else:
                print("Supabase directory already exists, skipping initialization")
            
            print("Setting up database schema...")

            # Clean migrations and create new schema
            migrations_dir = supabase_dir / 'migrations'
            if migrations_dir.exists():
                # Remove existing migrations
                for migration_file in migrations_dir.glob('*'):
                    if migration_file.is_file():
                        migration_file.unlink()
            
            print("Supabase new migration...")
            migration_result = subprocess.run(
                ['npx', 'supabase', 'migration', 'new', 'init_schema'],
                capture_output=True,
                text=True,
                timeout=300
            )
            assert migration_result.returncode == 0, f"Supabase new migration failed with return code {migration_result.returncode}"

            # Create new migration from schema
            schema_file = 'supabase_schema.sql'
            # Find the first migration file (should be the one we just created)
            migration_files = list(migrations_dir.glob('*'))
            assert len(migration_files) == 1
            target_migration = migration_files[0]
            shutil.copy(str(schema_file), str(target_migration))
            print(f"Copied schema to {target_migration}")
            
            # Copy sample data to seed file
            sample_data_file = Path('supabase_sample_data.sql')
            seed_file = supabase_dir / 'seed.sql'
            assert sample_data_file.exists()
            shutil.copy(str(sample_data_file), str(seed_file))
            print(f"Copied sample data to {seed_file}")
            
            # Reset database
            reset_result = subprocess.run(
                ['npx', 'supabase', 'db', 'reset'],
                capture_output=True,
                text=True,
                timeout=300
            )
            assert reset_result.returncode == 0, f"Supabase reset failed with return code {reset_result.returncode}"
                        
            # Go to frontend directory
            os.chdir(original_cwd)
            os.chdir(frontend_dir)
        
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
            
