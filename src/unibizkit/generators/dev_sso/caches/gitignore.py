from pathlib import Path


def generate(sso_dir: Path):
    (sso_dir / 'caches' / '.gitignore').write_text('*\n', encoding='utf-8')
