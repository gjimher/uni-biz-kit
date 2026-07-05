def generate(ctx) -> str:
    """nginx config: serve the SPA under base_uri and proxy <base>/api/ to Kong
    (stripping the prefix), mirroring the Vite dev proxy so the frontend build
    works unchanged (it resolves VITE_SUPABASE_URL against its own origin)."""
    prefix = ctx.base_prefix  # '' for root deploys
    redirect = ""
    if prefix:
        redirect = f"""
    location = / {{
        return 302 {prefix}/;
    }}
"""
    return f"""\
server {{
    listen 80;
    server_name _;
    client_max_body_size 64m;
    root /usr/share/nginx/html;
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
{redirect}
    location {prefix}/api/ {{
        proxy_pass http://kong:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $http_connection;
        proxy_read_timeout 120s;
    }}

    location {prefix}/ {{
        try_files $uri $uri/ {prefix}/index.html;
    }}
}}
"""
