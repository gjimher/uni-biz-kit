import os
import logging
import shutil
from pathlib import Path

from .context import Context
from . import eslintrc, index_html, package_json, vite_config
from .src import (
    supabase_client, index, auth_provider, data_provider, app,
    import_export_config, quick_edit_config, workflow_config
)
from .src.layout import (
    my_app_bar, my_layout, my_login_page, my_menu,
    my_set_password_page, user_profile_dialog, change_password_dialog,
    profile_completion_dialog
)
from .src.components import (
    title, reorderable_datagrid, recursive_parent_selector,
    custom_edit_toolbar, document_tab, workflow_selector, field_help_icon,
    markdown_input, import_export, quick_edit, workflow_tasks, deleted_snapshot_reference
)
from .src.resources import resource
from .src.presentation import model_js, router, custom_page
from .src.presentation.lib import (
    auth as lib_auth, validations as lib_validations, format as lib_format,
    workflow as lib_workflow, storage as lib_storage, index as lib_index,
    profile as lib_profile, payment as lib_payment,
)
from .. import dev_ports

logger = logging.getLogger(__name__)


def _write(path: Path, content: str):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _upsert_env(path: Path, values: dict[str, str]):
    existing = {}
    order = []
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                existing[key] = value.strip()
                order.append(key)
    for key, value in values.items():
        if key not in existing:
            order.append(key)
        existing[key] = value
    content = ''.join(f"{key}={existing[key]}\n" for key in dict.fromkeys(order))
    path.write_text(content, encoding='utf-8')


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
            deployment_config=getattr(schema_loader, 'deployment_config', None) or {},
            business_schema=schema_loader.business_schema,
            workflow_config=schema_loader.workflow_config,
            validations_config=getattr(schema_loader, 'validations_config', None) or {"validations": []},
            output_dir=self.output_dir,
        )

        model_dir = Path(schema_loader.schema_path).parent

        self._create_directory_structure(ctx)

        base_uri = ctx.deployment_config.get("base_uri", "/")

        # Root files
        _write(ctx.output_dir / "package.json", package_json.generate(ctx))
        _write(ctx.output_dir / "vite.config.js", vite_config.generate(base_uri))
        _write(ctx.output_dir / ".eslintrc.json", eslintrc.generate())
        _write(ctx.output_dir / "index.html", index_html.generate(ctx))
        base_prefix = base_uri.rstrip("/")
        # The app talks to Supabase through the Vite /api proxy. Keep this a relative
        # path (resolved against the serving origin in the browser) so the app works
        # on whatever host/port serves it — dev server or preview — with no hardcoded
        # port. Tests/tooling use the direct Kong URL in backend/.env instead.
        api_path = f"{base_prefix}/api"
        _upsert_env(ctx.output_dir / ".env.development", {
            "VITE_BASE_URL": f"http://localhost:{dev_ports.FRONTEND}{base_uri}",
            "VITE_BASE_URI": base_uri,
            "VITE_SUPABASE_URL": api_path,
        })

        # src/
        _write(ctx.output_dir / "src" / "supabaseClient.js", supabase_client.generate(ctx))
        _write(ctx.output_dir / "src" / "index.jsx", index.generate())
        _write(ctx.output_dir / "src" / "dataProvider.js", data_provider.generate(ctx))
        _write(ctx.output_dir / "src" / "importExportConfig.js", import_export_config.generate(ctx))
        _write(ctx.output_dir / "src" / "quickEditConfig.js", quick_edit_config.generate(ctx))

        has_auth_provider = False
        if ctx.security_config["authentication_required"]:
            _write(ctx.output_dir / "src" / "authProvider.js", auth_provider.generate(ctx))
            _write(ctx.output_dir / "src" / "layout" / "MySetPasswordPage.jsx", my_set_password_page.generate())
            _write(ctx.output_dir / "src" / "layout" / "MyAppBar.jsx", my_app_bar.generate())
            _write(ctx.output_dir / "src" / "layout" / "UserProfileDialog.jsx", user_profile_dialog.generate())
            _write(ctx.output_dir / "src" / "layout" / "ChangePasswordDialog.jsx", change_password_dialog.generate())
            _write(ctx.output_dir / "src" / "layout" / "MyLoginPage.jsx", my_login_page.generate(ctx))
            if profile_completion_dialog.gates(ctx):
                _write(ctx.output_dir / "src" / "layout" / "ProfileCompletionDialog.jsx",
                       profile_completion_dialog.generate(ctx))
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
        _write(ctx.output_dir / "src" / "components" / "field_help_icon.jsx", field_help_icon.generate())
        _write(ctx.output_dir / "src" / "components" / "import_export.jsx", import_export.generate())
        _write(ctx.output_dir / "src" / "components" / "quick_edit.jsx", quick_edit.generate())
        if any(f.get("on_delete") == "snapshot_data" for c in ctx.concepts for f in c["fields"]):
            _write(ctx.output_dir / "src" / "components" / "deleted_snapshot_reference.jsx", deleted_snapshot_reference.generate())
        if ctx.workflow_config["_concept_workflow"]:
            _write(ctx.output_dir / "src" / "workflowConfig.js", workflow_config.generate(ctx))
            _write(ctx.output_dir / "src" / "components" / "workflow_tasks.jsx", workflow_tasks.generate())
        if any(c.get("documents") and c["documents"]["enabled"] for c in ctx.concepts):
            _write(ctx.output_dir / "src" / "components" / "document_tab.jsx", document_tab.generate())
        if any(f["type"] == "markdown" for c in ctx.concepts for f in c["fields"]):
            _write(ctx.output_dir / "src" / "components" / "markdown_input.jsx", markdown_input.generate())

        # Resources (one per concept)
        for concept in ctx.concepts:
            resource_dir = ctx.output_dir / "src" / "resources" / concept["name"]
            resource_dir.mkdir(exist_ok=True)
            _write(resource_dir / f"{concept['name']}.jsx", resource.generate(ctx, concept))

        # Presentation system
        self._generate_presentation_system(ctx, model_dir)

        logger.info("React-Admin frontend generation completed")

    def _generate_presentation_system(self, ctx: Context, model_dir: Path):
        presentation_src = model_dir / "presentation"
        pres_dir = ctx.output_dir / "src" / "presentation"

        _write(pres_dir / "model.js", model_js.generate(ctx))
        _write(pres_dir / "PresentationRouter.jsx", router.generate(ctx))
        _write(pres_dir / "CustomPage.jsx", custom_page.generate())

        # Shared helper library for custom presentation pages (presentation/*.jsx).
        lib_dir = pres_dir / "lib"
        lib_dir.mkdir(exist_ok=True)
        _write(lib_dir / "auth.js", lib_auth.generate(ctx))
        _write(lib_dir / "profile.js", lib_profile.generate(ctx))
        _write(lib_dir / "payment.js", lib_payment.generate(ctx))
        _write(lib_dir / "validations.js", lib_validations.generate(ctx))
        _write(lib_dir / "format.js", lib_format.generate(ctx))
        _write(lib_dir / "workflow.js", lib_workflow.generate())
        _write(lib_dir / "storage.js", lib_storage.generate())
        _write(lib_dir / "index.js", lib_index.generate())

        # Auto-generate default layouts from presentation.json menu
        layouts_dir = pres_dir / "layouts"
        layouts_dir.mkdir(exist_ok=True)
        _write(layouts_dir / "sidebar-left.jsx", _generate_sidebar_layout())

        # Copy model pages
        pages_src = presentation_src / "pages"
        pages_dst = pres_dir / "pages"
        pages_dst.mkdir(exist_ok=True)
        if pages_src.exists():
            for page_file in pages_src.rglob("*"):
                if page_file.is_file():
                    target = pages_dst / page_file.relative_to(pages_src)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(page_file, target)

        # Copy custom layouts (override auto-generated)
        layouts_src = presentation_src / "layouts"
        if layouts_src.exists():
            for layout_file in layouts_src.iterdir():
                if layout_file.is_file():
                    shutil.copy2(layout_file, layouts_dir / layout_file.name)

        # Copy assets to public/presentation/ (served at /presentation/*)
        assets_src = presentation_src / "assets"
        if assets_src.exists():
            assets_dst = ctx.output_dir / "public" / "assets"
            assets_dst.mkdir(parents=True, exist_ok=True)
            for asset_file in assets_src.rglob("*"):
                if asset_file.is_file():
                    rel = asset_file.relative_to(assets_src)
                    dest = assets_dst / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(asset_file, dest)

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
        (src_dir / "presentation").mkdir(exist_ok=True)
        (src_dir / "presentation" / "pages").mkdir(exist_ok=True)
        (src_dir / "presentation" / "layouts").mkdir(exist_ok=True)

        self._generate_index_html(ctx)

    def _generate_index_html(self, ctx: Context):
        _write(ctx.output_dir / "index.html", index_html.generate(ctx))


def _generate_sidebar_layout() -> str:
    return """import React from 'react';
import { Link } from 'react-router-dom';
import { model } from '../model';

export default function SidebarLeft({ frontmatter, children }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', fontFamily: 'sans-serif' }}>
      <nav style={{
        width: 220,
        borderRight: '1px solid #e0e0e0',
        padding: '16px 12px',
        background: '#fafafa',
        flexShrink: 0,
      }}>
        <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '1rem' }}>{model.appName}</h3>
        </Link>
        {model.menu.map(group => (
          <div key={group.label} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#999', textTransform: 'uppercase', marginBottom: 4 }}>
              {group.label}
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {(group.children ?? []).map(item => (
                <li key={item.label} style={{ marginBottom: 2 }}>
                  {item.concept ? (
                    <a href={`#/admin/${item.concept}`} style={{ color: '#1976d2', textDecoration: 'none', fontSize: '0.9rem' }}>
                      {item.label}
                    </a>
                  ) : (
                    <span style={{ color: '#333', fontSize: '0.9rem' }}>{item.label}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div style={{ marginTop: 16, borderTop: '1px solid #e0e0e0', paddingTop: 12 }}>
          <a href="#/admin" style={{ color: '#555', fontSize: '0.9rem', textDecoration: 'none' }}>
            ⚙ Panel de Admin
          </a>
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, minWidth: 0 }}>
        {frontmatter?.title && (
          <h1 style={{ marginTop: 0, fontSize: '1.5rem' }}>{frontmatter.title}</h1>
        )}
        {children}
      </main>
    </div>
  );
}
"""
