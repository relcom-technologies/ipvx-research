"""Export the public document tree without source, Git, CI or local state."""
from pathlib import Path
import shutil
import sys


def copy_public(source, destination):
    source, destination = Path(source).resolve(), Path(destination)
    files = [*source.glob('*.html'), source / 'governance.json']
    for directory in ('assets', 'data', 'rfc'):
        files.extend(p for p in (source / directory).rglob('*') if p.is_file() or p.is_symlink())
    if not (source / 'index.html').is_file():
        raise ValueError('Public index is missing')
    for file in files:
        if file.is_symlink() or not file.resolve().is_relative_to(source):
            raise ValueError('Non-regular public source refused')
        target = destination / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        target.chmod(0o644)


if __name__ == '__main__':
    copy_public(*sys.argv[1:])
