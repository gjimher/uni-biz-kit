from pathlib import Path


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-reset-schema-and-data.py"
    with open(script, 'w', encoding='utf-8') as f:
        f.write("""\
#!/usr/bin/python3
\"\"\"Reset the local Supabase database: reload schema, seed data and auth users.\"\"\"
import sys
from pathlib import Path
if sys.prefix == sys.base_prefix:
    sys.exit(
        f"Error: run this script with the project's virtual environment Python.\\n"
        f"  python bin/{Path(__file__).name}\\n"
        f"(not python3 or direct execution)"
    )

import argparse
import json
import os
import shutil
import urllib.request
import urllib.error

parser = argparse.ArgumentParser(description="Reset local Supabase database.")
parser.add_argument('-f', '--force', action='store_true', help="Skip confirmation prompt")
args = parser.parse_args()

root_dir = Path(__file__).parent.parent
backend_dir = root_dir / 'backend'
frontend_dir = root_dir / 'frontend'
supabase_dir = backend_dir / 'supabase'

if not supabase_dir.exists():
    sys.exit("Error: backend/supabase does not exist. Run dev-supabase-start.py first.")

if not args.force:
    answer = input("This will wipe all data and reload schema + seed. Are you sure? [y/N] ")
    if answer.strip().lower() != 'y':
        print("Aborted.")
        sys.exit(0)

def parse_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()
    return env

import psycopg2

# Copy schema into migration file
migrations_dir = supabase_dir / 'migrations'
schema_file = backend_dir / 'supabase_schema.sql'
migration_files = sorted(migrations_dir.glob('*'))
if not migration_files:
    sys.exit("Error: no migration files found in supabase/migrations/")
shutil.copy(schema_file, migration_files[0])
print(f"Copied schema -> {migration_files[0].name}")

# Copy sample data to seed file
sample_data_file = backend_dir / 'supabase_sample_data.sql'
seed_file = supabase_dir / 'seed.sql'
shutil.copy(sample_data_file, seed_file)
print("Copied sample data -> supabase/seed.sql")

# Connect and reset DB
backend_env = parse_env(backend_dir / '.env')
db_url = backend_env.get('DB_URL')
if not db_url:
    sys.exit("Error: DB_URL not found in backend/.env")

service_role_key = backend_env.get('SUPABASE_SERVICE_ROLE_KEY')
frontend_env = parse_env(frontend_dir / '.env.development')
api_url = frontend_env.get('VITE_SUPABASE_URL')

conn = psycopg2.connect(db_url)
conn.autocommit = True
with conn.cursor() as cur:
    # Empty document storage buckets BEFORE dropping tables so the cleanup
    # trigger can still delete from *_document tables while they exist.
    if service_role_key and api_url:
        cur.execute("SELECT id FROM storage.buckets WHERE id LIKE '%-documents'")
        doc_buckets = [row[0] for row in cur.fetchall()]
        for bucket_id in doc_buckets:
            req = urllib.request.Request(
                f"{api_url}/storage/v1/bucket/{bucket_id}/empty",
                data=b'{}',
                headers={
                    'Authorization': f'Bearer {service_role_key}',
                    'Content-Type': 'application/json',
                    'apikey': service_role_key,
                },
                method='POST',
            )
            try:
                with urllib.request.urlopen(req):
                    print(f"  Emptied storage bucket: {bucket_id}")
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8')
                if e.code != 404:
                    print(f"  Warning: could not empty {bucket_id}: {e.code} {body}")

    print("Dropping all tables in public schema...")
    cur.execute(\"\"\"
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;\"\"\")

    print("Cleaning auth.users...")
    cur.execute("DELETE FROM auth.users;")

    print("Loading schema...")
    cur.execute(schema_file.read_text())

    print("Loading seed data...")
    cur.execute(seed_file.read_text())

conn.close()

# Create auth users via API
security_file = root_dir / 'security_extended.json'
if security_file.exists():
    security_data = json.loads(security_file.read_text())
    auth_users = security_data.get('users', [])

    print(f"Creating {len(auth_users)} auth user(s)...")
    for user in auth_users:
        email = user['email']
        password = user['password']
        data = json.dumps({
            'email': email,
            'password': password,
            'email_confirm': True,
            'app_metadata': {'roles': user.get('roles', [])},
        }).encode('utf-8')
        req = urllib.request.Request(
            f"{api_url}/auth/v1/admin/users",
            data=data,
            headers={
                'Authorization': f'Bearer {service_role_key}',
                'Content-Type': 'application/json',
                'apikey': service_role_key,
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req):
                print(f"  Created: {email}")
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            if e.code == 422 and 'User already exists' in body:
                print(f"  Already exists: {email}")
            else:
                print(f"  Error creating {email}: {e.code} {body}")

print("Reset complete.")
""")
    script.chmod(0o755)
