from pathlib import Path
from .constants import REALM, KDC_PORT, KADMIN_PORT


def generate(sso_dir: Path):
    (sso_dir / 'krb5-host.conf').write_text(_content(), encoding='utf-8')


def _content() -> str:
    return f"""\
[libdefaults]
    default_realm = {REALM}
    dns_lookup_realm = false
    dns_lookup_kdc = false
    rdns = false

[realms]
    {REALM} = {{
        kdc = localhost:{KDC_PORT}
        admin_server = localhost:{KADMIN_PORT}
    }}

[domain_realm]
    .dev.local = {REALM}
    dev.local = {REALM}
"""
