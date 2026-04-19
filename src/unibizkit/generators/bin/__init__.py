from pathlib import Path
from . import dev_supabase_create, dev_supabase_remove, dev_supabase_reset_schema_and_data


def generate(bin_dir: Path):
    dev_supabase_create.generate(bin_dir)
    dev_supabase_remove.generate(bin_dir)
    dev_supabase_reset_schema_and_data.generate(bin_dir)
