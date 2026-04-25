from pathlib import Path
from .constants import REALM


def generate(sso_dir: Path):
    (sso_dir / 'krb5.conf').write_text(_content(), encoding='utf-8')


def _content() -> str:
    return f"""\
[libdefaults]
    default_realm = {REALM}
    dns_lookup_realm = false
    dns_lookup_kdc = false

[realms]
    {REALM} = {{
        kdc = kdc:88
        admin_server = kdc:749
    }}

[domain_realm]
    .dev.local = {REALM}
    dev.local = {REALM}
"""
