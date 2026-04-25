from pathlib import Path
from typing import Any, Dict, List
from . import docker_compose, krb5_conf, krb5_host_conf, kdc_conf
from .caches import gitignore
from .kdc import dockerfile, entrypoint


def generate(sso_dir: Path, users: List[Dict[str, Any]]):
    sso_dir.mkdir(exist_ok=True)
    (sso_dir / 'kdc').mkdir(exist_ok=True)
    (sso_dir / 'caches').mkdir(exist_ok=True)

    docker_compose.generate(sso_dir)
    krb5_conf.generate(sso_dir)
    krb5_host_conf.generate(sso_dir)
    kdc_conf.generate(sso_dir)
    gitignore.generate(sso_dir)
    dockerfile.generate(sso_dir)
    entrypoint.generate(sso_dir, users)
