import pytest

from patch_files import file_manifest, prepare_patch
from release_update import REPOSITORY, atomic_json, current_state
from scripts.build_patch import build


def install_fixture(root, version, files):
    folder = root / 'versions' / version
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    atomic_json(root / 'current.json', {'current': version})
    atomic_json(folder / 'release.json', {
        'version': version, 'repository': REPOSITORY, 'launcher_protocol': 1, 'platform': 'windows-x64'})
    return folder


def test_patch_only_ships_changes_and_preserves_the_active_install(tmp_path):
    root, full, bundle = (tmp_path / name for name in ('installed', 'full', 'delta'))
    old = install_fixture(root, '3.4.6', {'WorkSpaceApp.exe': b'old exe', 'db/ledger': b'original', 'obsolete': b''})
    new = install_fixture(full, '3.4.7', {'WorkSpaceApp.exe': b'new exe', 'db/ledger': b'original', 'new': b'new'})
    build(root, full, bundle)
    assert set(file_manifest(bundle / 'changed')) == {'WorkSpaceApp.exe', 'new', 'release.json'}
    target = root / 'versions' / '3.4.7'
    (old / 'db/ledger').write_bytes(b'damaged')
    with pytest.raises(ValueError):
        prepare_patch(root, bundle, '3.4.7')
    assert not target.exists() and current_state(root)['current'] == '3.4.6'
    (old / 'db/ledger').write_bytes(b'original')
    prepare_patch(root, bundle, '3.4.7')
    prepare_patch(root, bundle, '3.4.7')
    assert file_manifest(target) == file_manifest(new) and (old / 'obsolete').exists()
    atomic_json(root / 'current.json', {'current': '3.4.5'})
    with pytest.raises(ValueError):
        prepare_patch(root, bundle, '3.4.7')
