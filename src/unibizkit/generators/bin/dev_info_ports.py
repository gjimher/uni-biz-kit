from pathlib import Path
from .. import dev_ports


def generate(bin_dir: Path):
    script = bin_dir / 'dev-info-ports.py'
    script.write_text(_content(), encoding='utf-8')
    script.chmod(0o755)


def _content() -> str:
    rows = [
        (0, dev_ports.FRONTEND, "React dev server (Vite)"),
        (1, dev_ports.VITE_PREVIEW, "Vite preview (E2E tests)"),
        (2, dev_ports.CHROME_DEBUG, "Chrome remote debugging (SSO)"),
        (3, dev_ports.EDGE_INSPECTOR, "Edge Runtime inspector (Deno)"),
        (10, dev_ports.SMTP, "SMTP mock"),
        (30, dev_ports.KC_PORT, "Keycloak web (SSO)"),
        (31, dev_ports.KC_MGMT_PORT, "Keycloak management"),
        (32, dev_ports.KDC_PORT, "KDC (Kerberos)"),
        (33, dev_ports.KADMIN_PORT, "Kadmin (Kerberos)"),
        (40, dev_ports.SUPABASE_API, "Supabase API"),
        (41, dev_ports.SUPABASE_DB, "Supabase DB (PostgreSQL)"),
        (42, dev_ports.SUPABASE_SHADOW, "Supabase shadow DB (migrations)"),
        (43, dev_ports.SUPABASE_STUDIO, "Supabase Studio"),
        (44, dev_ports.SUPABASE_INBUCKET, "Supabase Inbucket (email UI)"),
        (45, dev_ports.SUPABASE_ANALYTICS, "Supabase Analytics"),
        (46, dev_ports.SUPABASE_POOLER, "Supabase Pooler (PgBouncer)"),
    ]
    return f"""#!/usr/bin/python3
\"\"\"Print the development port layout baked into this generated app.\"\"\"

BASE_PORT = {dev_ports.BASE}
ROWS = {rows!r}


def main():
    print(f"Development base port: {{BASE_PORT}}")
    print()
    print(f"{{'Offset':<8}} {{'Port':<6}} Service")
    print(f"{{'-' * 8}} {{'-' * 6}} {{'-' * 40}}")
    for offset, port, service in ROWS:
        print(f"base+{{offset:<2}} {{port:<6}} {{service}}")


if __name__ == "__main__":
    main()
"""
