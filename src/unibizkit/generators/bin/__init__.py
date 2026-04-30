from pathlib import Path
from typing import Any, Dict
from .. import dev_sso
from . import (
    dev_supabase_start, dev_supabase_remove, dev_supabase_reset_schema_and_data,
    dev_sso_start, dev_sso_chrome, dev_sso_stop, dev_sso_remove,
    dev_smtp_mock,
)


def generate(bin_dir: Path, security_config: Dict[str, Any]):
    dev_supabase_start.generate(bin_dir)
    dev_supabase_remove.generate(bin_dir)
    dev_supabase_reset_schema_and_data.generate(bin_dir)
    dev_smtp_mock.generate(bin_dir)

    sso_config = security_config["sso"]
    if sso_config["enabled"]:
        users = security_config.get('users', [])
        sso_dir = bin_dir.parent / 'dev-sso'
        dev_sso.generate(sso_dir, users)
        dev_sso_start.generate(bin_dir)
        dev_sso_chrome.generate(bin_dir)
        dev_sso_stop.generate(bin_dir, sso_dir)
        dev_sso_remove.generate(bin_dir, sso_dir)
