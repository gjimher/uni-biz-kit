import os
import logging
from pathlib import Path

from .context import Context
from . import eslintrc, index_html, package_json, vite_config
from .src import supabase_client, index, auth_provider, data_provider, app
from .src.layout import (
    my_app_bar, my_layout, my_login_page, my_menu,
    my_set_password_page, user_profile_dialog, change_password_dialog
)
from .src.components import (
    title, reorderable_datagrid, recursive_parent_selector,
    custom_edit_toolbar, document_tab, workflow_selector
)
from .src.resources import resource

logger = logging.getLogger(__name__)


def _write(path: Path, content: str):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


class ReactAdminGenerator:
    def __init__(self, schema_loader, output_dir: str = "react-admin-app"):
        self.schema_loader = schema_loader
        self.output_dir = Path(output_dir)

    def generate_frontend(self):
        logger.info(f"Generating React-Admin frontend in {self.output_dir}")

        schema_loader = self.schema_loader
        concepts = schema_loader.get_all_concepts()
        concept_map = {c["name"]: c for c in concepts}

        ctx = Context(
            concepts=concepts,
            concept_map=concept_map,
            presentation_config=schema_loader.presentation_config,
            system_config=getattr(schema_loader, 'system_config', None) or {},
            security_config=schema_loader.security_config,
            business_schema=schema_loader.business_schema,
            output_dir=self.output_dir,
        )

        self._create_directory_structure(ctx)

        # Root files
        _write(ctx.output_dir / "package.json", package_json.generate())
        _write(ctx.output_dir / "vite.config.js", vite_config.generate())
        _write(ctx.output_dir / ".eslintrc.json", eslintrc.generate())
        _write(ctx.output_dir / "index.html", index_html.generate(ctx))

        # src/
        _write(ctx.output_dir / "src" / "supabaseClient.js", supabase_client.generate())
        _write(ctx.output_dir / "src" / "index.jsx", index.generate())
        _write(ctx.output_dir / "src" / "dataProvider.js", data_provider.generate(ctx))

        has_auth_provider = False
        if ctx.security_config["authentication_required"]:
            _write(ctx.output_dir / "src" / "authProvider.js", auth_provider.generate(ctx))
            _write(ctx.output_dir / "src" / "layout" / "MySetPasswordPage.jsx", my_set_password_page.generate())
            _write(ctx.output_dir / "src" / "layout" / "MyAppBar.jsx", my_app_bar.generate())
            _write(ctx.output_dir / "src" / "layout" / "UserProfileDialog.jsx", user_profile_dialog.generate())
            _write(ctx.output_dir / "src" / "layout" / "ChangePasswordDialog.jsx", change_password_dialog.generate())
            if ctx.security_config["registration"]["allow"]:
                _write(ctx.output_dir / "src" / "layout" / "MyLoginPage.jsx", my_login_page.generate(ctx))
            has_auth_provider = True

        has_custom_menu = False
        if ctx.presentation_config.get("menu"):
            _write(ctx.output_dir / "src" / "layout" / "MyMenu.jsx", my_menu.generate(ctx))
            _write(ctx.output_dir / "src" / "layout" / "MyLayout.jsx", my_layout.generate(has_auth_provider))
            has_custom_menu = True

        _write(ctx.output_dir / "src" / "App.jsx", app.generate(ctx, has_custom_menu, has_auth_provider))

        # Components
        _write(ctx.output_dir / "src" / "components" / "title.jsx", title.generate())
        _write(ctx.output_dir / "src" / "components" / "reorderable_datagrid.jsx", reorderable_datagrid.generate())
        _write(ctx.output_dir / "src" / "components" / "recursive_parent_selector.jsx", recursive_parent_selector.generate())
        _write(ctx.output_dir / "src" / "components" / "custom_edit_toolbar.jsx", custom_edit_toolbar.generate())
        _write(ctx.output_dir / "src" / "components" / "workflow_selector.jsx", workflow_selector.generate())
        if any(c.get("documents") and c["documents"]["enabled"] for c in ctx.concepts):
            _write(ctx.output_dir / "src" / "components" / "document_tab.jsx", document_tab.generate())

        # Resources (one per concept)
        for concept in ctx.concepts:
            resource_dir = ctx.output_dir / "src" / "resources" / concept["name"]
            resource_dir.mkdir(exist_ok=True)
            _write(resource_dir / f"{concept['name']}.jsx", resource.generate(ctx, concept))

        logger.info("React-Admin frontend generation completed")

    def _create_directory_structure(self, ctx: Context):
        ctx.output_dir.mkdir(exist_ok=True)

        src_dir = ctx.output_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    (Path(root) / file).unlink()
        else:
            src_dir.mkdir()

        (src_dir / "resources").mkdir(exist_ok=True)
        (src_dir / "components").mkdir(exist_ok=True)
        (src_dir / "utils").mkdir(exist_ok=True)
        (src_dir / "layout").mkdir(exist_ok=True)

        self._generate_index_html(ctx)

    def _generate_index_html(self, ctx: Context):
        _write(ctx.output_dir / "index.html", index_html.generate(ctx))
