from pathlib import Path


def generate(bin_dir: Path):
    script = bin_dir / "dev-supabase-reset-schema-and-data.py"
    with open(script, 'w', encoding='utf-8') as f:
        f.write("""\
#!/usr/bin/python3
\"\"\"Reset the local Supabase database: reload schema, seed data and auth users.

Leaves the database exactly as generated, wiping anything else. Requires a
running instance (dev-supabase-start.py first). Steps:

* Asks for confirmation unless -f/--force is given (all data is wiped).
* Copies the generated backend/supabase_schema.sql into the initial migration
  and supabase_seed_data_dev.sql into supabase/seed.sql.
* Connects to the database (DB_URL from backend/.env) and:
  - empties the document storage buckets (*-documents),
  - drops every table in the public schema,
  - deletes all rows in auth.users,
  - reloads the schema and the seed data.
* Uploads the seed documents (e.g. product images) through the Storage API so
  their metadata is created by the database triggers.
* Creates the auth users from security_extended.json through the Admin API,
  with their roles in app_metadata (existing users are kept).
\"\"\"
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
import base64
import urllib.request
import urllib.error
import urllib.parse

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
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

# Copy development seed data to seed file
seed_data_dev_file = backend_dir / 'supabase_seed_data_dev.sql'
seed_file = supabase_dir / 'seed.sql'
shutil.copy(seed_data_dev_file, seed_file)
print("Copied development seed data -> supabase/seed.sql")

# Connect and reset DB
backend_env = parse_env(backend_dir / '.env')
db_url = backend_env.get('DB_URL')
if not db_url:
    sys.exit("Error: DB_URL not found in backend/.env")

service_role_key = backend_env.get('SUPABASE_SERVICE_ROLE_KEY')
# Reach Supabase (Kong) directly via backend/.env, not the Vite proxy, so reset
# works without a running dev server.
api_url = backend_env.get('SUPABASE_URL')

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

# Upload seed documents through the Storage API so binary content is stored
# and document metadata is created by the database trigger.
seed_data_file = root_dir / 'seed_data_extended.json'
if seed_data_file.exists() and service_role_key and api_url:
    seed_data = json.loads(seed_data_file.read_text())
    concepts_file = root_dir / 'concepts_extended.json'
    concept_docs = {}
    if concepts_file.exists():
        concepts_data = json.loads(concepts_file.read_text())
        concept_docs = {
            c['name']: c.get('documents', {})
            for c in concepts_data.get('concepts', [])
        }
    seed_documents = []
    with conn.cursor() as cur:
        for concept, records in seed_data.get('records', {}).items():
            for index, record in enumerate(records, start=1):
                seed_key = str(record.get('id', f"__{concept}_{index}"))
                documents = record.get('documents', [])
                if not documents:
                    continue
                cur.execute(
                    "SELECT db_id FROM unibizkit_seed_data_ids WHERE concept = %s AND seed_key = %s",
                    (concept, seed_key),
                )
                row = cur.fetchone()
                if not row:
                    print(f"  Warning: could not resolve seed document owner {concept}/{seed_key}")
                    continue
                for document in documents:
                    seed_documents.append({
                        **document,
                        'concept': concept,
                        'record_id': row[0],
                    })
    print(f"Uploading {len(seed_documents)} seed document(s)...")
    for doc in seed_documents:
        concept = doc['concept']
        bucket_id = f"{concept}-documents"
        record_id = doc['record_id']
        tag = doc['tag']
        name = doc['name']
        version = doc.get('version', 1)
        content_type = doc.get('content_type', 'application/octet-stream')
        bucket_versioned = concept_docs.get(concept, {}).get('versioned', False)
        path_parts = [str(record_id), tag]
        if bucket_versioned:
            path_parts.append(f"v{version}")
        path_parts.append(name)
        object_path = '/'.join(path_parts)
        quoted_path = urllib.parse.quote(object_path, safe='/')
        try:
            content = base64.b64decode(doc['content_base64'])
        except Exception as e:
            print(f"  Error decoding {concept}/{record_id}/{name}: {e}")
            continue
        req = urllib.request.Request(
            f"{api_url}/storage/v1/object/{bucket_id}/{quoted_path}",
            data=content,
            headers={
                'Authorization': f'Bearer {service_role_key}',
                'Content-Type': content_type,
                'apikey': service_role_key,
                'x-upsert': 'true',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req):
                print(f"  Uploaded: {bucket_id}/{object_path}")
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            print(f"  Error uploading {bucket_id}/{object_path}: {e.code} {body}")

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
