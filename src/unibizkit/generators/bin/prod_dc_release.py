from pathlib import Path

from unibizkit import release


def generate(bin_dir: Path):
    # Verbatim copy of unibizkit.release (stdlib-only) so the generated bin/
    # scripts keep working without the unibizkit package installed.
    (bin_dir / "prod_dc_release.py").write_text(Path(release.__file__).read_text())
