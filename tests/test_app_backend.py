"""
Backend Integration Test for App App Generation

This test generates a complete app application backend and sets up the database.
"""

import pytest
import json
import os
import sys
import shutil
import time
import re
import subprocess
import urllib.request
from pathlib import Path
from unittest.mock import patch
from unibizkit.cli import CLI
from dotenv import load_dotenv
import psycopg2
from textwrap import dedent

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
        schema_path = Path('models/test-app/concepts.json').resolve()
        output_dir = Path('test-app').resolve()
        
        print("Executing uni-biz-kit: generating a complete app application from schema")
        with patch('sys.argv', ['uni-biz-kit', 'models/test-app', '--output-dir', str(output_dir)]):
            # Should not raise an exception
            cli.run()
        
        # Check that output directory was created
        assert output_dir.exists()

        backend_dir = output_dir / 'backend'
        frontend_dir = output_dir / 'frontend'
        
        # Change directories
        original_cwd = os.getcwd()
        
        try:
            os.chdir(backend_dir)
            # remove with: npx supabase stop --no-backup ; rm -rf supabase
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
                
                print("Changing Supabase project_id to ubk_test_app and ports from 54xxx to 55xxx in supabase/config.toml")
                config_path = Path("supabase/config.toml")
                text = config_path.read_text()
                text = text.replace('project_id = "backend"', 'project_id = "ubk_test_app"')
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
                
                print("Supabase new migration...")
                migration_result = subprocess.run(
                    ['npx', 'supabase', 'migration', 'new', 'init_schema'],
                    stdout=sys.stdout, 
                    stderr=sys.stderr, 
                    timeout=300
                )
                assert migration_result.returncode == 0, f"Supabase new migration failed with return code {migration_result.returncode}"

                # Create .env file with supabase credentials
                print("Creating .env files...")
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
                db_url = status_data.get('DB_URL', '')
                service_role_key = status_data.get('SERVICE_ROLE_KEY', '')

                # Change back to original directory
                os.chdir(original_cwd)

                # Write .env files
                (backend_dir / ".env").write_text(f"DB_URL={db_url}\nSUPABASE_URL={api_url}\nSUPABASE_SERVICE_ROLE_KEY={service_role_key}\n")
                (frontend_dir / ".env").write_text(f"REACT_APP_SUPABASE_URL={api_url}\nREACT_APP_SUPABASE_KEY={anon_key}\n")
            else:
                print("Supabase directory already exists, skipping initialization")
            
            print("Setting up database schema...")
            os.chdir(original_cwd)
            os.chdir(backend_dir)
            migrations_dir = supabase_dir / 'migrations'
            schema_file = Path('supabase_schema.sql')
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
            
            load_dotenv(".env")
            db_url = os.getenv("DB_URL")
            assert db_url
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                print("Dropping all tables in schema public...")
                cur.execute(dedent(f"""
                    DO $$
                    DECLARE
                        r RECORD;
                    BEGIN
                        FOR r IN (
                            SELECT tablename
                            FROM pg_tables
                            WHERE schemaname = 'public'
                        ) LOOP
                            EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                        END LOOP;
                    END $$;"""))
                
                print("Cleaning auth.users...")
                cur.execute("DELETE FROM auth.users;")

                print("Loading schema")
                cur.execute(schema_file.read_text())
                print("Loading seed data")
                cur.execute(seed_file.read_text())

            # Create users via API
            print("Creating Auth users via API...")
            auth_users_file = backend_dir / "supabase_auth_users.json"
            if auth_users_file.exists():
                with open(auth_users_file, 'r') as f:
                    auth_users = json.load(f)
                
                load_dotenv(backend_dir / ".env", override=True)
                service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
                # We need the API_URL from the status, but it's also in frontend/.env as REACT_APP_SUPABASE_URL
                load_dotenv(frontend_dir / ".env", override=True)
                api_url = os.getenv("REACT_APP_SUPABASE_URL")

                for user in auth_users:
                    email = user["email"]
                    password = user["password"]
                    print(f"  Creating user: {email}")
                    
                    # Supabase Admin API to create user
                    url = f"{api_url}/auth/v1/admin/users"
                    data = json.dumps({
                        "email": email,
                        "password": password,
                        "email_confirm": True
                    }).encode('utf-8')
                    
                    req = urllib.request.Request(
                        url, 
                        data=data, 
                        headers={
                            'Authorization': f'Bearer {service_role_key}',
                            'Content-Type': 'application/json',
                            'apikey': service_role_key
                        },
                        method='POST'
                    )
                    
                    try:
                        with urllib.request.urlopen(req) as response:
                            res_body = response.read().decode('utf-8')
                            print(f"    User {email} created successfully.")
                    except urllib.error.HTTPError as e:
                        error_body = e.read().decode('utf-8')
                        if e.code == 422 and "User already exists" in error_body:
                            print(f"    User {email} already exists, skipping.")
                        else:
                            print(f"    Error creating user {email}: {e.code} {error_body}")

        finally:
            os.chdir(original_cwd)
