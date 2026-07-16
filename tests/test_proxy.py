"""
Proxy-kind model generation tests.

A 'proxy' model (models/ubk-app) has no app sources: only deployment.jsonc with a
'proxy' section, index.md and assets/. It generates a single Caddy container that
terminates HTTPS, serves the landing page and reverse-proxies the referenced app
models by their base_uri. These tests drive generation in-process (like
test_frontend.py) and assert on the generated artifacts.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from unibizkit.cli import CLI
from unibizkit.schema_loader import SchemaValidationError, SchemaLoader


def _write(path: Path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content))
    else:
        path.write_text(content)


def _fake_app_model(models_dir: Path, name: str, deployment: dict):
    """Minimal app model: only what the proxy cross-validation inspects
    (concepts.jsonc must exist; deployment.jsonc is the source of base_uri/port)."""
    _write(models_dir / name / "concepts.jsonc", {})
    _write(models_dir / name / "deployment.jsonc", {"prod_versioning": "dev", **deployment})


class TestProxyGeneration:
    def test_generate_proxy_app(self, tmp_path):
        """Generate the real models/ubk-app and assert on every artifact."""
        output_dir = tmp_path / "ubk-app"
        with patch("sys.argv", ["uni-biz-kit", "models/ubk-app", "--output-dir", str(output_dir)]):
            CLI().run()

        assert output_dir.exists()

        # deployment_extended.json: resolved targets + domain.
        dep = json.loads((output_dir / "deployment_extended.json").read_text())
        assert dep["proxy"]["domain"] == "www.unibizkit.dev"
        assert dep["_proxy_targets"] == [
            {"model": "b2c-app", "base_uri": "/b2c/", "port": 3050},
            {"model": "intranet-app", "base_uri": "/intranet/", "port": 3100},
        ]

        # Caddyfile: TLS-ALPN-01 only, no HTTP-01, prefix-preserving reverse proxy.
        caddyfile = (output_dir / "prod" / "docker" / "caddy" / "Caddyfile").read_text()
        assert "www.unibizkit.dev {" in caddyfile
        assert "disable_http_challenge" in caddyfile
        assert "auto_https disable_redirects" in caddyfile
        assert "redir /b2c /b2c/ 308" in caddyfile
        assert "reverse_proxy /b2c/* 127.0.0.1:3050" in caddyfile
        assert "redir /intranet /intranet/ 308" in caddyfile
        assert "reverse_proxy /intranet/* 127.0.0.1:3100" in caddyfile
        assert "file_server" in caddyfile

        # Landing page: GitHub link, demo link, screenshot images.
        index_html = (output_dir / "prod" / "docker" / "caddy" / "site" / "index.html").read_text()
        assert "https://github.com/gjimher/uni-biz-kit" in index_html
        assert 'href="/b2c/"' in index_html
        assert "<img" in index_html and "assets/" in index_html
        # assets/ tree copied into the site.
        assets_dir = output_dir / "prod" / "docker" / "caddy" / "site" / "assets"
        assert assets_dir.is_dir()
        for asset in re.findall(r'src="assets/([^"]+)"', index_html):
            assert (assets_dir / asset).is_file()

        # Compose: host network, cert volume, versioned caddy image.
        compose = (output_dir / "prod" / "docker" / "docker-compose.template.yml").read_text()
        assert "network_mode: host" in compose
        assert "caddy-data:" in compose
        assert "localhost:5000/ubk-app/caddy:__VERSION__" in compose

        # Dockerfile builds the caddy image with the site baked in.
        dockerfile = (output_dir / "prod" / "docker" / "caddy" / "Dockerfile").read_text()
        assert dockerfile.startswith("FROM caddy:")

        # bin/: production scripts only, no dev-* scripts.
        bin_files = sorted(p.name for p in (output_dir / "bin").iterdir())
        assert bin_files == [
            "prod-dc-check-infra.py",
            "prod-dc-publish.py",
            "prod-dc-remove.py",
            "prod-dc-up.py",
            "prod_dc_common.py",
            "prod_dc_release.py",
        ]
        publish_script = (output_dir / "bin" / "prod-dc-publish.py").read_text()
        assert 'parser.add_argument("--dry-run", action="store_true"' in publish_script
        assert "publish_git_tag()" in publish_script
        assert 'releases/{version}.json' in publish_script
        assert 'git("tag", "-a"' in publish_script
        up_script = (output_dir / "bin" / "prod-dc-up.py").read_text()
        assert 'parser.add_argument("--version", help=' in up_script
        assert "tagged_versions" in up_script
        assert 'parser.add_argument("--force"' not in publish_script
        assert 'parser.add_argument("--force"' not in up_script
        assert not (output_dir / "bin" / "dev-supabase-start.py").exists()

        # The generated bin/ must stay self-contained (stdlib + colocated helpers).
        for script in ("prod-dc-publish.py", "prod-dc-up.py", "prod_dc_release.py"):
            assert "from unibizkit" not in (output_dir / "bin" / script).read_text()

        publish_help = subprocess.run(
            [sys.executable, output_dir / "bin" / "prod-dc-publish.py", "-h"],
            text=True, capture_output=True, check=True,
        ).stdout
        assert "Publish this generated model without activating it" in publish_help
        assert "Steps:" in publish_help
        assert "Idempotency:" in publish_help
        assert "never applies SQL" in publish_help

        # No app output.
        assert not (output_dir / "frontend").exists()
        assert not (output_dir / "backend").exists()

    def test_prod_origin_drives_production_public_urls(self, tmp_path):
        models_dir = tmp_path / "models"
        app_dir = models_dir / "shop-app"
        _write(app_dir / "concepts.jsonc", {
            "version": "1.0.0",
            "name": "Shop",
            "concepts": [{
                "name": "product",
                "id_presentation": {"fields": ["name"]},
                "fields": [{"name": "name", "type": "string", "required": True}],
            }],
        })
        _write(app_dir / "presentation.jsonc", {})
        _write(app_dir / "security.jsonc", {"authentication_required": False})
        _write(app_dir / "system.jsonc", {
            "smtp": {
                "host": "mail.internal",
                "port": 2525,
                "from_email": "noreply@example.com",
            },
        })
        _write(app_dir / "deployment.jsonc", {
            "prod_versioning": "dev",
            "base_uri": "/shop",
            "prod_origin": "https://www.example.com",
            "prod_base_port": 4050,
        })

        output_dir = tmp_path / "shop-app"
        with patch("sys.argv", [
            "uni-biz-kit", str(app_dir), "--output-dir", str(output_dir), "--skip-frontend",
        ]):
            CLI().run()

        compose = (output_dir / "prod" / "docker" / "docker-compose.template.yml").read_text()
        assert "GOTRUE_SITE_URL: https://www.example.com/shop/" in compose
        assert "API_EXTERNAL_URL: https://www.example.com/shop/api" in compose
        assert "GOTRUE_SMTP_HOST: mail.internal" in compose
        assert "GOTRUE_SMTP_PORT: 2525" in compose
        assert "GOTRUE_SMTP_USER" not in compose
        assert "GOTRUE_SMTP_PASS" not in compose
        assert "SMTP_USER" not in compose
        assert "SMTP_PASS" not in compose
        assert "http://${PUBLIC_HOST}:4050/shop" not in compose

        dev_config = (output_dir / "backend" / "supabase_config_dev.toml").read_text()
        assert "[auth.email.smtp]" in dev_config
        # Generated apps only target unauthenticated SMTP servers (no real
        # credentials anywhere), but the pinned supabase CLI rejects the dev
        # config unless smtp user/pass exist: fixed placeholders, never values
        # taken from the model.
        assert 'user = "mock"' in dev_config
        assert 'pass = "mock"' in dev_config

        publish_script = (output_dir / "bin" / "prod-dc-publish.py").read_text()
        up_script = (output_dir / "bin" / "prod-dc-up.py").read_text()
        assert 'prod_origin = (cfg.get("prod_origin") or "").rstrip("/")' in publish_script
        assert 'f"{prod_origin}{base_uri}" if prod_origin' in publish_script
        assert '"VITE_BASE_URL": public_base' in publish_script
        assert 'parser.add_argument("--force", action="store_true"' in up_script

    def test_app_model_rejects_proxy_section(self):
        """An app model (has concepts) whose deployment.jsonc carries a proxy section is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "concepts.jsonc", {
                "version": "1.0.0", "name": "X",
                "concepts": [{
                    "name": "c", "id_presentation": {"fields": ["f"]},
                    "fields": [{"name": "f", "type": "string", "required": True}],
                }],
            })
            _write(root / "presentation.jsonc", {})
            _write(root / "security.jsonc", {"authentication_required": False})
            _write(root / "deployment.jsonc", {
                "prod_versioning": "dev",
                "base_uri": "/x",
                "proxy": {"domain": "d", "models": ["y"]},
            })
            with pytest.raises(SchemaValidationError, match="proxy"):
                SchemaLoader(str(root / "concepts.jsonc")).load_and_validate()

    def test_proxy_model_rejects_app_sources(self):
        """A proxy model (deployment.jsonc + proxy, no concepts) must not carry app sources."""
        with tempfile.TemporaryDirectory() as tmp:
            models_dir = Path(tmp) / "models"
            proxy_dir = models_dir / "ubk-app"
            _write(proxy_dir / "deployment.jsonc", {
                "prod_versioning": "dev",
                "proxy": {"domain": "d", "models": ["b2c-app"]},
            })
            _write(proxy_dir / "index.md", "# X")
            _write(proxy_dir / "security.jsonc", {})  # stray app source
            _fake_app_model(models_dir, "b2c-app", {"base_uri": "/b2c"})
            with pytest.raises(SchemaValidationError, match="app source"):
                CLI()._handle_generate_proxy(proxy_dir, Path(tmp) / "out", emit=True)

    def test_proxy_rejects_duplicate_ports(self):
        """Two referenced app models sharing a prod_base_port are rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            models_dir = Path(tmp) / "models"
            proxy_dir = models_dir / "ubk-app"
            _write(proxy_dir / "deployment.jsonc", {
                "prod_versioning": "dev",
                "proxy": {"domain": "d", "models": ["a-app", "b-app"]},
            })
            _write(proxy_dir / "index.md", "# X")
            # Distinct base_uris (so the base_uri check passes) but both default port 3000.
            _fake_app_model(models_dir, "a-app", {"base_uri": "/a"})
            _fake_app_model(models_dir, "b-app", {"base_uri": "/b"})
            with pytest.raises(SchemaValidationError, match="prod_base_port"):
                CLI()._handle_generate_proxy(proxy_dir, Path(tmp) / "out", emit=True)

    def test_proxy_rejects_root_base_uri_target(self):
        """A referenced app at base_uri '/' would shadow the landing and is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            models_dir = Path(tmp) / "models"
            proxy_dir = models_dir / "ubk-app"
            _write(proxy_dir / "deployment.jsonc", {
                "prod_versioning": "dev",
                "proxy": {"domain": "d", "models": ["root-app"]},
            })
            _write(proxy_dir / "index.md", "# X")
            _fake_app_model(models_dir, "root-app", {})  # base_uri defaults to "/"
            with pytest.raises(SchemaValidationError, match="shadow"):
                CLI()._handle_generate_proxy(proxy_dir, Path(tmp) / "out", emit=True)
