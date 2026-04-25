from pathlib import Path


def generate(sso_dir: Path):
    (sso_dir / 'kdc' / 'Dockerfile').write_text(_content(), encoding='utf-8')


def _content() -> str:
    return """\
FROM debian:bookworm-slim

RUN apt-get update && \\
    DEBIAN_FRONTEND=noninteractive apt-get install -y \\
        krb5-kdc \\
        krb5-admin-server \\
        krb5-user \\
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh

EXPOSE 88/udp 88/tcp 749/tcp

ENTRYPOINT ["/entrypoint.sh"]
"""
