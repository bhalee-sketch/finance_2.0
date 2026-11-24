"""Compare two actual Windows release payloads and package changed application files."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_files import file_manifest
from release_update import current_state, release_path, version_key


def build(base_root, payload, output):
    base = current_state(base_root)['current']
    version = current_state(payload)['current']
    if version_key(version) <= version_key(base):
        raise ValueError('패치 대상은 설치된 버전보다 최신이어야 합니다.')
    old = file_manifest(release_path(base_root, base))
    folder = release_path(payload, version)
    files = file_manifest(folder)
    output.mkdir(parents=True)
    for name, digest in files.items():
        if old.get(name) != digest:
            dest = output / 'changed' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder / name, dest)
    (output / 'patch.json').write_text(json.dumps(dict(base=base, version=version, files=files),
                                                  ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('base_root', 'payload', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    build(args.base_root, args.payload, args.output)
