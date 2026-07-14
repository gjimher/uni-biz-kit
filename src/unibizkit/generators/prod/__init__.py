"""Production docker-compose deployment artifacts.

Generates <output>/prod/docker/: a versioned docker-compose template plus the
Dockerfiles and configs needed to build the app's images. The generated
bin/prod-* scripts build the images, push them to a registry running on the
production host and deploy the compose file there (see bin/prod-publish.py).

The stack is a slim self-hosted Supabase (db, kong, auth, rest, storage,
edge functions) plus an nginx serving the built SPA and a one-shot provision
container that loads the schema, seed data, seed documents and auth users.
"""
import json
from pathlib import Path
from typing import Any, Dict

from .constants import IMAGES, FRONTEND_OFFSET, KONG_OFFSET, DB_OFFSET, STUDIO_OFFSET
from . import docker_compose, dockerfiles, functions_main, kong_config, nginx_conf, provision_script


class ProdContext:
    def __init__(self, app_id: str, deployment_config: Dict[str, Any],
                 security_config: Dict[str, Any], system_config: Dict[str, Any]):
        self.app_id = app_id  # output dir name: registry namespace and ~/ubk/<app_id>
        self.base_uri = deployment_config["base_uri"]          # normalized, ends with /
        self.base_prefix = self.base_uri.rstrip("/")            # '' for root deploys
        self.prod_origin = (deployment_config.get("prod_origin") or "").rstrip("/")
        self.base_port = deployment_config["prod_base_port"]
        self.frontend_port = self.base_port + FRONTEND_OFFSET
        self.kong_port = self.base_port + KONG_OFFSET
        self.db_port = self.base_port + DB_OFFSET
        self.studio_port = self.base_port + STUDIO_OFFSET
        self.allow_registration = security_config["registration"]["allow"]
        self.smtp = self._resolve_smtp(deployment_config, system_config)
        self.smtp_uses_host_gateway = (
            self.smtp is not None and self.smtp["host"] in ("127.0.0.1", "localhost")
        )

    def _resolve_smtp(self, deployment_config: Dict[str, Any],
                      system_config: Dict[str, Any]) -> Dict[str, Any] | None:
        prod_smtp_keys = ("prod_smtp_server", "prod_smtp_port", "prod_smtp_from")
        has_prod_smtp_override = any(deployment_config.get(key) is not None for key in prod_smtp_keys)

        smtp = {
            "host": "127.0.0.1",
            "port": 25,
            "from_email": "noreply@localhost",
            "user": None,
            "password": None,
        }
        smtp.update(system_config.get("smtp", {}))

        if has_prod_smtp_override:
            if deployment_config.get("prod_smtp_server") is not None:
                smtp["host"] = deployment_config["prod_smtp_server"]
            if deployment_config.get("prod_smtp_port") is not None:
                smtp["port"] = deployment_config["prod_smtp_port"]
            if deployment_config.get("prod_smtp_from") is not None:
                smtp["from_email"] = deployment_config["prod_smtp_from"]
            return smtp

        # A loopback SMTP host in system.jsonc points at the dev mail catcher,
        # which does not exist in prod: auto-confirm emails instead of sending them.
        return None if smtp["host"] in ("127.0.0.1", "localhost") else smtp


def generate(output_dir: Path, app_id: str, deployment_config: Dict[str, Any],
             security_config: Dict[str, Any], system_config: Dict[str, Any]):
    ctx = ProdContext(app_id, deployment_config, security_config, system_config)
    docker_dir = output_dir / "prod" / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "backend" / "release_migration.sql", "SELECT 1; -- no release migration prepared\n")

    # Whitelist .dockerignore: image builds use the app root as context, which
    # would otherwise upload node_modules and the local supabase state.
    _write(output_dir / ".dockerignore", """\
*
!frontend/dist
!backend/supabase_schema.sql
!backend/release_migration.sql
!backend/supabase_seed_data_dev.sql
!backend/deployed_data_runtime.py
!backend/supabase/functions
!security_extended.json
!seed_data_extended.json
!deployed_data_extended.json
!deployed_data_extended_schema.json
!concepts_extended.json
!prod/docker
prod/docker/docker-compose-*.yml
""")

    _write(docker_dir / "vendor-images.json", json.dumps({
        "vendor/gotrue": IMAGES["auth"],
        "vendor/postgrest": IMAGES["rest"],
        "vendor/storage-api": IMAGES["storage"],
        "vendor/studio": IMAGES["studio"],
        "vendor/postgres-meta": IMAGES["meta"],
    }, indent=2) + "\n")

    _write(docker_dir / "docker-compose.template.yml", docker_compose.generate(ctx))
    _write(docker_dir / "frontend" / "Dockerfile", dockerfiles.frontend(ctx))
    _write(docker_dir / "frontend" / "nginx.conf", nginx_conf.generate(ctx))
    _write(docker_dir / "db" / "Dockerfile", dockerfiles.db())
    _write(docker_dir / "db" / "init-scripts" / "99-ubk-roles.sql", dockerfiles.db_roles_sql())
    _write(docker_dir / "db" / "init-scripts" / "99-ubk-jwt.sql", dockerfiles.db_jwt_sql())
    _write(docker_dir / "db" / "init-scripts" / "99-ubk-zz-ownership.sql", dockerfiles.db_ownership_sql())
    _write(docker_dir / "kong" / "Dockerfile", dockerfiles.kong())
    _write(docker_dir / "kong" / "temp.yml", kong_config.generate())
    _write(docker_dir / "functions" / "Dockerfile", dockerfiles.functions())
    _write(docker_dir / "functions" / "main" / "index.ts", functions_main.generate())
    _write(docker_dir / "provision" / "Dockerfile", dockerfiles.provision())
    _write(docker_dir / "provision" / "provision.py", provision_script.generate())


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
