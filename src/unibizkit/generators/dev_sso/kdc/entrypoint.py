from pathlib import Path
from typing import Any, Dict, List
from ..constants import REALM


def generate(sso_dir: Path, users: List[Dict[str, Any]]):
    path = sso_dir / 'kdc' / 'entrypoint.sh'
    path.write_text(_content(users), encoding='utf-8')
    path.chmod(0o755)


def _content(users: List[Dict[str, Any]]) -> str:
    addprinc_lines = []
    for user in users:
        username = user['email'].split('@')[0]
        password = user['password']
        addprinc_lines.append(
            f'    kadmin.local -q "addprinc -pw {password} {username}@{REALM}"'
        )
    addprinc_block = '\n'.join(addprinc_lines)

    return f"""\
#!/bin/bash
set -e

if [ ! -f "/var/lib/krb5kdc/principal" ]; then
    echo "Initializing Kerberos database..."
    kdb5_util create -s -r {REALM} -P "kdc-master-key"
    echo "*/admin@{REALM} *" > /etc/krb5kdc/kadm5.acl

    kadmin.local -q "addprinc -pw admin admin/admin@{REALM}"
{addprinc_block}

    kadmin.local -q "addprinc -randkey HTTP/keycloak.dev.local@{REALM}"
    kadmin.local -q "ktadd -k /keytabs/keycloak.keytab HTTP/keycloak.dev.local@{REALM}"
    chmod 644 /keytabs/keycloak.keytab
    echo "Kerberos database initialized."
fi

echo "Starting KDC..."
exec krb5kdc -n
"""
