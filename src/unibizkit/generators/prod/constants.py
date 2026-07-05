# Pinned service images (aligned with the versions the Supabase CLI uses in dev).
IMAGES = {
    "db": "public.ecr.aws/supabase/postgres:17.6.1.106",
    "auth": "public.ecr.aws/supabase/gotrue:v2.188.1",
    "rest": "public.ecr.aws/supabase/postgrest:v14.10",
    "storage": "public.ecr.aws/supabase/storage-api:v1.54.1",
    "kong": "public.ecr.aws/supabase/kong:2.8.1",
    "edge_runtime": "public.ecr.aws/supabase/edge-runtime:v1.73.13",
    "studio": "public.ecr.aws/supabase/studio:2026.04.27-sha-4afbe9c",
    "meta": "public.ecr.aws/supabase/postgres-meta:v0.96.4",
    "nginx": "nginx:1.27-alpine",
    "python": "python:3.12-slim",
}

# Port offsets on top of prod_base_port (same layout as generators/dev_ports.py).
FRONTEND_OFFSET = 0
KONG_OFFSET = 40
DB_OFFSET = 41
STUDIO_OFFSET = 43

# The remote registry always listens on the production host's loopback.
REGISTRY = "localhost:5000"
