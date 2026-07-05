def generate() -> str:
    """provision.py running inside the one-shot provision container."""
    return '''\
"""One-shot production provisioner.

Waits until the stack is healthy (db reachable, GoTrue and Storage migrations
applied, Kong answering), then on the FIRST run loads the application schema,
the seed data, the seed documents (through the Storage API) and the auth users
(through the GoTrue admin API). Subsequent runs detect the marker table
unibizkit_prod_releases and only re-ensure the auth users exist, so the
container is safe to restart on every `docker-compose up`.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import psycopg2

DB_URL = os.environ["DB_URL"]
API_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
VERSION = os.environ.get("UBK_VERSION", "unknown")

WAIT_TIMEOUT = 300


def log(msg):
    print(msg, flush=True)


def wait_for(description, check):
    deadline = time.time() + WAIT_TIMEOUT
    while True:
        try:
            if check():
                log(f"ready: {description}")
                return
        except Exception as e:
            last = e
        if time.time() > deadline:
            sys.exit(f"Timed out waiting for {description}")
        time.sleep(3)


def db_connect():
    return psycopg2.connect(DB_URL)


def table_exists(cur, schema, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    return cur.fetchone() is not None


def api_request(method, path, body=None, content_type="application/json", extra_headers=None):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "apikey": SERVICE_ROLE_KEY,
        "Content-Type": content_type,
    }
    headers.update(extra_headers or {})
    req = urllib.request.Request(f"{API_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, resp.read().decode()


# --- Wait for the stack ------------------------------------------------------
def _db_ready():
    conn = db_connect()
    conn.close()
    return True


def _auth_migrated():
    with db_connect() as conn, conn.cursor() as cur:
        return table_exists(cur, "auth", "users")


def _storage_migrated():
    with db_connect() as conn, conn.cursor() as cur:
        return table_exists(cur, "storage", "buckets")


def _kong_ready():
    status, _ = api_request("GET", "/auth/v1/health")
    return status == 200


wait_for("database", _db_ready)
wait_for("auth migrations (auth.users)", _auth_migrated)
wait_for("storage migrations (storage.buckets)", _storage_migrated)
wait_for("kong -> auth", _kong_ready)

conn = db_connect()
conn.autocommit = True

with conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.unibizkit_prod_releases (
            version TEXT PRIMARY KEY,
            provisioned BOOLEAN NOT NULL DEFAULT false,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        REVOKE ALL ON public.unibizkit_prod_releases FROM anon, authenticated;
    """)
    cur.execute("SELECT version FROM public.unibizkit_prod_releases WHERE provisioned")
    provisioned = [row[0] for row in cur.fetchall()]

first_run = not provisioned

if first_run:
    log("First provision: loading schema...")
    with conn.cursor() as cur:
        cur.execute(open("supabase_schema.sql").read())
    log("Loading seed data...")
    with conn.cursor() as cur:
        cur.execute(open("supabase_seed_data_dev.sql").read())
else:
    log(f"Database already provisioned by version(s): {', '.join(provisioned)} — "
        "skipping schema and seed (versions are additive; data is preserved).")

# --- Seed documents (first run only) -----------------------------------------
if first_run and os.path.exists("seed_data_extended.json"):
    seed_data = json.load(open("seed_data_extended.json"))
    concept_docs = {}
    if os.path.exists("concepts_extended.json"):
        concepts_data = json.load(open("concepts_extended.json"))
        concept_docs = {c["name"]: c.get("documents", {}) for c in concepts_data.get("concepts", [])}
    seed_documents = []
    with conn.cursor() as cur:
        for concept, records in seed_data.get("records", {}).items():
            for index, record in enumerate(records, start=1):
                seed_key = str(record.get("id", f"__{concept}_{index}"))
                documents = record.get("documents", [])
                if not documents:
                    continue
                cur.execute(
                    "SELECT db_id FROM unibizkit_seed_data_ids WHERE concept = %s AND seed_key = %s",
                    (concept, seed_key),
                )
                row = cur.fetchone()
                if not row:
                    log(f"  Warning: could not resolve seed document owner {concept}/{seed_key}")
                    continue
                for document in documents:
                    seed_documents.append({**document, "concept": concept, "record_id": row[0]})
    log(f"Uploading {len(seed_documents)} seed document(s)...")
    for doc in seed_documents:
        concept = doc["concept"]
        bucket_id = f"{concept}-documents"
        path_parts = [str(doc["record_id"]), doc["tag"]]
        if concept_docs.get(concept, {}).get("versioned", False):
            path_parts.append(f"v{doc.get('version', 1)}")
        path_parts.append(doc["name"])
        object_path = urllib.parse.quote("/".join(path_parts), safe="/")
        try:
            content = base64.b64decode(doc["content_base64"])
            api_request(
                "POST", f"/storage/v1/object/{bucket_id}/{object_path}",
                body=content,
                content_type=doc.get("content_type", "application/octet-stream"),
                extra_headers={"x-upsert": "true"},
            )
            log(f"  Uploaded: {bucket_id}/{object_path}")
        except urllib.error.HTTPError as e:
            log(f"  Error uploading {bucket_id}/{object_path}: {e.code} {e.read().decode()}")

# --- Auth users (idempotent: always ensure they exist) ------------------------
if os.path.exists("security_extended.json"):
    auth_users = json.load(open("security_extended.json")).get("users", [])
    log(f"Ensuring {len(auth_users)} auth user(s) exist...")
    for user in auth_users:
        body = {
            "email": user["email"],
            "password": user["password"],
            "email_confirm": True,
            "app_metadata": {"roles": user.get("roles", [])},
        }
        try:
            api_request("POST", "/auth/v1/admin/users", body=body)
            log(f"  Created: {user['email']}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            if "already been registered" in detail or "User already exists" in detail:
                log(f"  Already exists: {user['email']}")
            else:
                log(f"  Error creating {user['email']}: {e.code} {detail}")

with conn.cursor() as cur:
    cur.execute(
        """INSERT INTO public.unibizkit_prod_releases (version, provisioned)
           VALUES (%s, true) ON CONFLICT (version) DO NOTHING""",
        (VERSION,),
    )
conn.close()
log(f"Provision complete (version {VERSION}).")
'''
