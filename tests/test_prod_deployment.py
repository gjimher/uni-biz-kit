"""Opt-in destructive production deployment smoke test."""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from unibizkit.schema_loader import _load_jsonc_file


def _run(args, *, cwd, timeout=1800, check=True):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if check:
        assert result.returncode == 0, f"command failed: {' '.join(map(str, args))}"
    return result


def _remove_previous_test_worktrees(root):
    tmp_dir = (root / "tmp").resolve()
    prefix = "ubk-deploy-test-"
    listing = _run(["git", "worktree", "list", "--porcelain"], cwd=root).stdout
    for block in listing.strip().split("\n\n"):
        fields = dict(
            line.split(" ", 1) for line in block.splitlines() if " " in line
        )
        path = Path(fields.get("worktree", "")).resolve()
        if path.parent != tmp_dir or not path.name.startswith(prefix):
            continue
        _run(["git", "worktree", "remove", "--force", path], cwd=root, check=False)
        branch_ref = fields.get("branch", "")
        if branch_ref.startswith("refs/heads/"):
            _run(["git", "branch", "-D", branch_ref.removeprefix("refs/heads/")], cwd=root, check=False)

    if tmp_dir.exists():
        for path in tmp_dir.glob(f"{prefix}*"):
            if path.is_dir():
                shutil.rmtree(path)

    for branch in _run(["git", "branch", "--list", f"{prefix}*", "--format=%(refname:short)"], cwd=root).stdout.splitlines():
        _run(["git", "branch", "-D", branch], cwd=root, check=False)


def _remove_remote_test_deployment(root):
    """Remove state left by an interrupted earlier smoke test."""
    _run([
        "ssh", "ubk-prod",
        "if [ -d ~/ubk/deploy-test-app ]; then "
        "cd ~/ubk/deploy-test-app; "
        "if [ -e docker-compose.yml ] || [ -L docker-compose.yml ]; then "
        "docker-compose down -v --remove-orphans; "
        "fi; "
        "cd; rm -rf ~/ubk/deploy-test-app; "
        "fi",
    ], cwd=root)


@pytest.mark.integration
@pytest.mark.timeout(3600)
def test_dev_then_git_tag_deployment(request):
    if not request.config.getoption("--slow-prod"):
        pytest.skip("requires explicit --slow-prod (uses and wipes ubk-prod ports 6000-6046)")

    root = Path(__file__).resolve().parents[1]
    _remove_previous_test_worktrees(root)
    _remove_remote_test_deployment(root)
    suffix = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"
    branch = f"ubk-deploy-test-{suffix}"
    worktree = root / "tmp" / branch
    model = worktree / "models" / "deploy-test-app"
    output = worktree / "deploy-test-app"
    tags_before = set(_run(["git", "tag", "--list", "prod-deploy-test-app-v*"], cwd=root).stdout.splitlines())
    deployed = False
    try:
        _run(["git", "worktree", "add", "-b", branch, worktree, "HEAD"], cwd=root)
        shutil.copytree(worktree / "models" / "test-dummy-app", model)
        (model / "deployment.jsonc").write_text(json.dumps({
            "$schema": "../../schemas/deployment_schema.json",
            "base_uri": "/deploy-test",
            "prod_dcd_ssh_srv": "ubk-prod",
            "prod_base_port": 6000,
            "prod_versioning": "dev",
        }, indent=2) + "\n")
        (model / "deployed_data.jsonc").write_text(json.dumps({
            "$schema": "../../schemas/deployed_data_schema.json",
            "concepts": [{
                "concept": "widget",
                "on_removed": "ignore",
                "records": [
                    {"name": "deployed-widget-a", "quantity": 11},
                    {"name": "deployed-widget-b", "quantity": 22},
                ],
            }],
        }, indent=2) + "\n")
        concepts_path = model / "concepts.jsonc"
        concepts = _load_jsonc_file(str(concepts_path))
        concepts["concepts"][0]["actions"] = [{
            "label": "Vendor check",
            "source": "vendor-check.js",
            "placement": ["edit"],
        }]
        concepts_path.write_text(json.dumps(concepts, indent=2) + "\n")
        actions_dir = model / "backend" / "actions"
        actions_dir.mkdir(parents=True)
        (actions_dir / "vendor-check.js").write_text(
            'import slugify from "npm:slugify@1.6.6";\n\n'
            'export async function run({ ids }) {\n'
            '  return { status: "ok", message: slugify(`widgets-${ids.join("-")}`) };\n'
            '}\n'
        )
        _run(["git", "add", "models/deploy-test-app"], cwd=worktree)
        _run(["git", "commit", "-m", "test: add temporary deployment model"], cwd=worktree)
        _run([sys.executable, "-m", "unibizkit.cli", "models/deploy-test-app", "--output-dir", output], cwd=worktree)
        _run([sys.executable, output / "bin" / "prod-dc-publish.py"], cwd=worktree)
        published_dev = _run(["ssh", "ubk-prod", "cat ~/ubk/deploy-test-app/releases/dev.json"], cwd=worktree)
        assert json.loads(published_dev.stdout)["version"] == "dev"
        assert _run([
            "ssh", "ubk-prod", "test ! -e ~/ubk/deploy-test-app/docker-compose.yml",
        ], cwd=worktree).returncode == 0
        _run([sys.executable, output / "bin" / "prod-dc-up.py", "--force"], cwd=worktree)
        deployed = True
        remote_dev = _run(["ssh", "ubk-prod", "cat ~/ubk/deploy-test-app/releases/dev.json"], cwd=worktree)
        assert json.loads(remote_dev.stdout)["version"] == "dev"
        _run([
            "ssh", "ubk-prod",
            "cd ~/ubk/deploy-test-app && "
            "docker-compose exec -T functions sh -c "
            "'test -n \"$(find /deno-dir -iname \"*slugify*\" -print -quit)\"'",
        ], cwd=worktree)

        deployment = json.loads((model / "deployment.jsonc").read_text())
        deployment["prod_versioning"] = "git-tag"
        (model / "deployment.jsonc").write_text(json.dumps(deployment, indent=2) + "\n")
        _run(["git", "add", "models/deploy-test-app/deployment.jsonc"], cwd=worktree)
        _run(["git", "commit", "-m", "test: enable tagged deployment"], cwd=worktree)
        _run([sys.executable, "-m", "unibizkit.cli", "models/deploy-test-app", "--output-dir", output], cwd=worktree)
        _run([sys.executable, output / "bin" / "prod-dc-publish.py"], cwd=worktree)
        assert _run([
            "ssh", "ubk-prod", "readlink ~/ubk/deploy-test-app/docker-compose.yml",
        ], cwd=worktree).stdout.strip() == "docker-compose-dev.yml"
        assert _run([
            "git", "tag", "--list", "prod-deploy-test-app-v1.0",
        ], cwd=worktree).stdout.strip() == "prod-deploy-test-app-v1.0"
        published_v1 = _run(["ssh", "ubk-prod", "cat ~/ubk/deploy-test-app/releases/v1.0.json"], cwd=worktree)
        assert json.loads(published_v1.stdout)["tag"] == "prod-deploy-test-app-v1.0"
        _run([sys.executable, output / "bin" / "prod-dc-up.py"], cwd=worktree)
        tag = "prod-deploy-test-app-v1.0"
        assert tag in _run(["git", "tag", "--list", tag], cwd=worktree).stdout
        remote_release = _run(["ssh", "ubk-prod", "cat ~/ubk/deploy-test-app/releases/v1.0.json"], cwd=worktree)
        metadata = json.loads(remote_release.stdout)
        assert metadata["tag"] == tag
        _run([
            "ssh", "ubk-prod", "python3 -c \"import urllib.request; "
            "assert urllib.request.urlopen('http://127.0.0.1:6000/deploy-test/', timeout=15).status == 200\"",
        ], cwd=worktree)

        compose_psql = (
            "cd ~/ubk/deploy-test-app && "
            "docker-compose exec -T db psql -U supabase_admin postgres"
        )
        deployed_values = compose_psql.replace(
            "psql -U supabase_admin postgres",
            "psql -At -U supabase_admin postgres -c \"SELECT name || ':' || quantity FROM widget WHERE name LIKE 'deployed-widget-%' ORDER BY name\"",
        )
        assert _run(["ssh", "ubk-prod", deployed_values], cwd=worktree).stdout.splitlines() == [
            "deployed-widget-a:11", "deployed-widget-b:22",
        ]
        damage_deployed = compose_psql.replace(
            "psql -U supabase_admin postgres",
            "psql -U supabase_admin postgres -c \"DELETE FROM widget WHERE name='deployed-widget-a'; UPDATE widget SET quantity=999 WHERE name='deployed-widget-b'\"",
        )
        _run(["ssh", "ubk-prod", damage_deployed], cwd=worktree)

        # A frontend-only amend has the same DB migration and may republish v1.0.
        presentation_path = model / "presentation.jsonc"
        presentation = json.loads(presentation_path.read_text())
        presentation["menu"][0]["label"] = "Inventory"
        presentation_path.write_text(json.dumps(presentation, indent=2) + "\n")
        _run(["git", "add", "models/deploy-test-app/presentation.jsonc"], cwd=worktree)
        _run(["git", "commit", "--amend", "--no-edit"], cwd=worktree)
        _run([sys.executable, "-m", "unibizkit.cli", "models/deploy-test-app", "--output-dir", output], cwd=worktree)
        _run([sys.executable, output / "bin" / "prod-dc-publish.py", "--republish"], cwd=worktree)
        assert _run(["git", "rev-list", "-n", "1", tag], cwd=worktree).stdout.strip() == _run(
            ["git", "rev-parse", "HEAD"], cwd=worktree
        ).stdout.strip()
        _run([sys.executable, output / "bin" / "prod-dc-up.py"], cwd=worktree)
        assert _run(["ssh", "ubk-prod", deployed_values], cwd=worktree).stdout.splitlines() == [
            "deployed-widget-a:11", "deployed-widget-b:22",
        ]

        # Preserve a non-seed row across the compatible minor migration.
        insert = compose_psql.replace(
            "psql -U supabase_admin postgres",
            "psql -U supabase_admin postgres -c \"INSERT INTO widget(name, quantity) VALUES ('kept-release-row', 7)\"",
        )
        _run(["ssh", "ubk-prod", insert], cwd=worktree)

        concepts_path = model / "concepts.jsonc"
        concepts = json.loads(concepts_path.read_text())
        concepts["concepts"][0]["fields"].append({"name": "note", "type": "string"})
        concepts_path.write_text(json.dumps(concepts, indent=2) + "\n")
        _run(["git", "add", "models/deploy-test-app/concepts.jsonc"], cwd=worktree)
        _run(["git", "commit", "--amend", "--no-edit"], cwd=worktree)
        _run([sys.executable, "-m", "unibizkit.cli", "models/deploy-test-app", "--output-dir", output], cwd=worktree)
        rejected = _run(
            [sys.executable, output / "bin" / "prod-dc-publish.py", "--republish"],
            cwd=worktree, check=False,
        )
        assert rejected.returncode != 0
        assert "migration is identical" in rejected.stdout + rejected.stderr

        # The same additive schema is valid as the next minor release.
        _run([sys.executable, output / "bin" / "prod-dc-publish.py"], cwd=worktree)
        note_before_up = compose_psql.replace(
            "psql -U supabase_admin postgres",
            "psql -At -U supabase_admin postgres -c \"SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='widget' AND column_name='note'\"",
        )
        assert "0" in _run(["ssh", "ubk-prod", note_before_up], cwd=worktree).stdout
        assert _run([
            "git", "tag", "--list", "prod-deploy-test-app-v1.1",
        ], cwd=worktree).stdout.strip() == "prod-deploy-test-app-v1.1"
        _run([sys.executable, output / "bin" / "prod-dc-up.py"], cwd=worktree)
        assert "prod-deploy-test-app-v1.1" in _run(
            ["git", "tag", "--list", "prod-deploy-test-app-v1.1"], cwd=worktree
        ).stdout
        count = compose_psql.replace(
            "psql -U supabase_admin postgres",
            "psql -At -U supabase_admin postgres -c \"SELECT count(*) FROM widget WHERE name='kept-release-row'\"",
        )
        assert "1" in _run(["ssh", "ubk-prod", count], cwd=worktree).stdout
        assert "1" in _run(["ssh", "ubk-prod", note_before_up], cwd=worktree).stdout

        # Removing a column is rejected for the next minor before deployment.
        concepts["concepts"][0]["fields"] = [
            field for field in concepts["concepts"][0]["fields"] if field["name"] != "quantity"
        ]
        concepts_path.write_text(json.dumps(concepts, indent=2) + "\n")
        seed_path = model / "seed_data.jsonc"
        seed_data = _load_jsonc_file(str(seed_path))
        for record in seed_data["records"]["widget"]:
            record.pop("quantity", None)
        seed_path.write_text(json.dumps(seed_data, indent=2) + "\n")
        deployed_data_path = model / "deployed_data.jsonc"
        deployed_data = _load_jsonc_file(str(deployed_data_path))
        for entry in deployed_data["concepts"]:
            if entry["concept"] == "widget":
                for record in entry["records"]:
                    record.pop("quantity", None)
        deployed_data_path.write_text(json.dumps(deployed_data, indent=2) + "\n")
        _run([
            "git", "add", "models/deploy-test-app/concepts.jsonc",
            "models/deploy-test-app/seed_data.jsonc",
            "models/deploy-test-app/deployed_data.jsonc",
        ], cwd=worktree)
        _run(["git", "commit", "-m", "test: introduce incompatible schema"], cwd=worktree)
        _run([sys.executable, "-m", "unibizkit.cli", "models/deploy-test-app", "--output-dir", output], cwd=worktree)
        incompatible = _run([sys.executable, output / "bin" / "prod-dc-publish.py"], cwd=worktree, check=False)
        assert incompatible.returncode != 0
        assert "incompatible minor migration" in incompatible.stdout + incompatible.stderr
    finally:
        if deployed and (output / "bin" / "prod-dc-remove.py").exists():
            _run([sys.executable, output / "bin" / "prod-dc-remove.py", "--force"], cwd=worktree, check=False)
        _remove_remote_test_deployment(root)
        tags_after = set(_run(["git", "tag", "--list", "prod-deploy-test-app-v*"], cwd=root).stdout.splitlines())
        for tag in tags_after - tags_before:
            _run(["git", "tag", "-d", tag], cwd=root, check=False)
        print(f"Test worktree retained for inspection: {worktree}")
