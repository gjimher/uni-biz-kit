"""
Backend Integration Test for Ecommerce App Generation

This test generates a complete ecommerce application backend and sets up the database.
"""

import pytest
import json
import os
import sys
import shutil
import time
import re
import subprocess
from pathlib import Path
from unittest.mock import patch
from unibizkit.cli import CLI


class TestEcommerceBackend:
    """Backend integration tests for ecommerce app generation."""
    
    @pytest.mark.integration
    @pytest.mark.timeout(600)  # 10 minutes timeout
    def test_generate_ecommerce_backend_and_setup_database(self):
        """Test generating a complete ecommerce app backend and setting up the database.
        
        This integration test:
        1. Generates a complete ecommerce application from schema
        2. Sets up Supabase database with schema and sample data
        3. Verifies the database setup is successful
        
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
        
        # Change to output directory
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
                    stdout=sys.stdout, 
                    stderr=sys.stderr, 
                    timeout=300
                )
                assert init_result.returncode == 0, f"Supabase init failed with {init_result=}"
                
                print("Changing Supabase ports from 54xxx to 55xxx in supabase/config.toml")
                config_path = Path("supabase/config.toml")
                text = config_path.read_text()
                text = re.sub(r"\b54(\d{3})\b", r"55\1", text)
                config_path.write_text(text)
                
                # Start supabase
                print("Starting Supabase...")
                start_result = subprocess.run(
                    ['npx', 'supabase', 'start'],
                    stdout=sys.stdout, 
                    stderr=sys.stderr, 
                    timeout=300
                )
                assert start_result.returncode == 0, f"Supabase start failed with {start_result=}"
                
                # Wait a bit for supabase to be ready
                time.sleep(10)
                
                # Create .env file with supabase credentials
                print("Creating .env file...")
                env_content = ""
                status_result = subprocess.run(
                    ['npx', 'supabase', 'status', '-o', 'json'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                assert status_result.returncode == 0, f"Could not get supabase status: {status_result=}"
                status_data = json.loads(status_result.stdout)
                api_url = status_data.get('API_URL', '')
                anon_key = status_data.get('ANON_KEY', '')
                
                env_content = f"REACT_APP_SUPABASE_URL={api_url}\nREACT_APP_SUPABASE_KEY={anon_key}\n"
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
                stdout=sys.stdout, 
                stderr=sys.stderr, 
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
            print("Executing: 'npx supabase db reset'")
            reset_result = subprocess.run(
                ['npx', 'supabase', 'db', 'reset'],
                stdout=sys.stdout, 
                stderr=sys.stderr, 
                timeout=300
            )
            assert reset_result.returncode == 0, f"Supabase reset failed with return code {reset_result.returncode}"
            
            print("✓ Ecommerce backend generated and database setup successfully!")
            
        finally:
            os.chdir(original_cwd)