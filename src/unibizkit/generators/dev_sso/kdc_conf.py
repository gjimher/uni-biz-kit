from pathlib import Path
from .constants import REALM


def generate(sso_dir: Path):
    (sso_dir / 'kdc.conf').write_text(_content(), encoding='utf-8')


def _content() -> str:
    return f"""\
[kdcdefaults]
    kdc_ports = 88
    kdc_tcp_ports = 88

[realms]
    {REALM} = {{
        acl_file = /etc/krb5kdc/kadm5.acl
        key_stash_file = /etc/krb5kdc/.k5.{REALM}
        max_life = 10h 0m 0s
        max_renewable_life = 7d 0h 0m 0s
    }}
"""
