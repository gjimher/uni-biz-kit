from pathlib import Path
from typing import Any, Dict
from .. import dev_sso
from . import (
    dev_supabase_start, dev_supabase_stop, dev_supabase_remove, dev_supabase_reset_schema_and_data,
    dev_supabase_call_edge_function, dev_deploy_data, dev_set_secret,
    dev_sso_start, dev_sso_chrome, dev_sso_stop, dev_sso_remove,
    dev_smtp_mock, dev_integration_odata_mock, dev_info_ports,
    prod_dc_common, prod_dc_release, prod_dc_check_infra, prod_dc_publish, prod_dc_up,
    prod_dc_remove, prod_dc_set_secret, prod_dc_up_proxy, prod_dc_remove_proxy,
)


def generate(bin_dir: Path, security_config: Dict[str, Any], base_uri: str = "/"):
    dev_supabase_start.generate(bin_dir, base_uri)
    dev_supabase_stop.generate(bin_dir)
    dev_supabase_remove.generate(bin_dir)
    dev_supabase_reset_schema_and_data.generate(bin_dir)
    dev_supabase_call_edge_function.generate(bin_dir)
    dev_deploy_data.generate(bin_dir)
    dev_set_secret.generate(bin_dir)
    dev_smtp_mock.generate(bin_dir)
    dev_integration_odata_mock.generate(bin_dir)
    dev_info_ports.generate(bin_dir)

    prod_dc_common.generate(bin_dir)
    prod_dc_release.generate(bin_dir)
    prod_dc_check_infra.generate(bin_dir)
    prod_dc_publish.generate(bin_dir)
    prod_dc_up.generate(bin_dir)
    prod_dc_remove.generate(bin_dir)
    prod_dc_set_secret.generate(bin_dir)
    # Legacy names (before the prod-dc- rename)
    for legacy in ("prod_common.py", "prod-check-infra.py", "prod-publish.py",
                   "prod-up.py", "prod-remove.py"):
        legacy_path = bin_dir / legacy
        if legacy_path.exists():
            legacy_path.unlink()

    sso_config = security_config["sso"]
    if sso_config["enabled"]:
        users = security_config.get('users', [])
        sso_dir = bin_dir.parent / 'dev-sso'
        dev_sso.generate(sso_dir, users)
        dev_sso_start.generate(bin_dir)
        dev_sso_chrome.generate(bin_dir)
        dev_sso_stop.generate(bin_dir, sso_dir)
        dev_sso_remove.generate(bin_dir, sso_dir)


def generate_proxy(bin_dir: Path):
    """bin/ scripts for a 'proxy' kind model: only the prod-dc-* deploy scripts
    (no dev-* scripts — a proxy has no local Supabase/SSO to run)."""
    prod_dc_common.generate(bin_dir)
    prod_dc_release.generate(bin_dir)
    prod_dc_check_infra.generate(bin_dir)
    prod_dc_publish.generate(bin_dir)
    prod_dc_up_proxy.generate(bin_dir)
    prod_dc_remove_proxy.generate(bin_dir)
