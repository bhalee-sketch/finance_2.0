"""Build and verify a new version tree using files from an installed release."""
import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
from tempfile import TemporaryDirectory

from release_update import current_state, read_json, release_metadata, release_path, version_key


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_manifest(folder):
    return {path.relative_to(folder).as_posix(): file_hash(path)
            for path in sorted(folder.rglob('*')) if path.is_file()}


def prepare_patch(root, bundle, expected_version):
    root, bundle = Path(root), Path(bundle)
    manifest = read_json(bundle / 'patch.json')
    base, version = manifest['base'], manifest['version']
    if (version != expected_version or version_key(version) <= version_key(base)
            or current_state(root)['current'] != base):
        raise ValueError('설치된 버전과 패치의 기준 버전이 다릅니다.')
    old = release_path(root, base)
    target = release_path(root, version)
    files = manifest['files']
    if 'release.json' not in files or 'WorkSpaceApp.exe' not in files:
        raise ValueError('패치 파일 목록을 확인하세요.')
    if target.exists():
        if file_manifest(target) != files or release_metadata(target)['version'] != version:
            raise ValueError('대상 버전 폴더를 확인하세요.')
        return
    with TemporaryDirectory(prefix='.patch-', dir=target.parent) as temp:
        stage = Path(temp) / 'app'
        for name, digest in files.items():
            rel = PureWindowsPath(name)
            if (rel.anchor or not rel.parts or rel.as_posix() != name or '..' in rel.parts
                    or any(':' in part or part.endswith(('.', ' ')) or PureWindowsPath(part).is_reserved()
                           for part in rel.parts) or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise ValueError('패치 파일 목록을 확인하세요.')
            source = bundle / 'changed' / name
            if not source.exists():
                source = old / name
            dest = stage / name
            dest.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(source, dest)
            if file_hash(dest) != digest:
                raise ValueError(f'설치 파일이 일치하지 않습니다. {name}')
        if release_metadata(stage)['version'] != version:
            raise ValueError('패치 대상 버전을 확인하세요.')
        os.rename(stage, target)
