"""Build the Windows x64 application payload and stable launcher with Python 3.12."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from build_source_release import LEDGER, ROOT, RUNTIME_DATA, allowed, compact_ledger

sys.path.insert(0, str(ROOT))
from release_update import REPOSITORY, version_key


def build(version, output):
    version_key(version)
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        raise ValueError('Build with Windows x64 Python 3.12.')
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new build output directory.')
    output.mkdir(parents=True)
    assets = output/'runtime-data'
    for name in sorted(RUNTIME_DATA):
        target = assets/name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == LEDGER:
            compact_ledger(ROOT/name, target)
        else:
            shutil.copyfile(ROOT/name, target)
    for source in (ROOT/'data'/'appendices'/'originals').iterdir():
        name = source.relative_to(ROOT).as_posix()
        if source.is_file() and allowed(name):
            target = assets/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def freeze(entry, name, options):
        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--noupx',
            '--name', name, '--icon', str(ROOT/'assets'/'workspace.ico'),
            '--specpath', str(output/'spec'), '--workpath', str(output/'work'),
            '--distpath', str(output/'frozen'), *options, str(ROOT/entry),
        ], cwd=ROOT, check=True)

    freeze('packaged_entry.py', 'WorkSpaceApp', [
        '--onedir', '--add-data', f'{ROOT / "assets"};assets',
        '--add-data', f'{ROOT / "templates"};templates',
        '--add-data', f'{assets / "data"};data',
        '--add-data', f'{ROOT / "scripts" / "inspect_school.ps1"};scripts',
        '--collect-data', 'playwright', '--hidden-import', 'greenlet',
    ])
    freeze('installed_launcher.py', 'WorkSpace', ['--onefile'])
    installer = output/'installer'
    installed = installer/'versions'/version
    installed.parent.mkdir(parents=True)
    (output/'frozen'/'WorkSpaceApp').rename(installed)
    (output/'frozen'/'WorkSpace.exe').rename(installer/'WorkSpace.exe')
    (installed/'release.json').write_text(json.dumps({
        'version': version, 'repository': REPOSITORY, 'platform': 'windows-x64',
        'launcher_protocol': 1, 'update_channel': 'setup',
    }), encoding='utf-8')
    (installer/'current.json').write_text(json.dumps({'current': version}), encoding='utf-8')
    print(installer)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    build(arguments.version, arguments.output)
