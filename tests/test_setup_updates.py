from hashlib import sha256
from io import BytesIO
from unittest.mock import patch

import pytest

from release_update import SETUP_API, UpdateError, download_setup, latest_setup


def release(version, *, prerelease=False, draft=False, checksum=True, state='uploaded'):
    filename = f'WorkSpace-Setup-{version}-x64.exe'
    assets = [{'name': filename, 'state': state}]
    if checksum:
        assets.append({'name': filename + '.sha256', 'state': 'uploaded'})
    return {'tag_name': 'v' + version, 'draft': draft, 'prerelease': prerelease, 'assets': assets}


def test_latest_setup_selects_newest_complete_stable_release():
    releases = [
        release('3.4.0', prerelease=True), release('3.3.9', draft=True),
        release('3.3.8', checksum=False), release('3.3.7', state='new'),
        release('3.3.5'), release('3.3.6'), release('3.3.3'),
    ]
    with patch('release_update.GithubClient') as client:
        client.return_value.json.return_value = releases
        assert latest_setup('3.3.4') == (
            '3.3.6',
            'https://github.com/bhalee-sketch/finance_2.0/releases/download/v3.3.6/WorkSpace-Setup-3.3.6-x64.exe',
        )
        client.assert_called_once_with(api=SETUP_API)


def test_latest_setup_ignores_installed_and_older_releases():
    with patch('release_update.GithubClient.json', return_value=[release('3.3.4'), release('3.3.3')]):
        assert latest_setup('3.3.4') is None

@pytest.mark.parametrize('valid', [True, False])
def test_setup_download_is_exposed_only_after_hash_verification(tmp_path, valid):
    filename = 'WorkSpace-Setup-3.3.5-x64.exe'
    url = 'https://github.com/bhalee-sketch/finance_2.0/releases/download/v3.3.5/' + filename
    payload = b'installer data'
    digest = sha256(payload if valid else b'other').hexdigest()
    responses = [BytesIO(f'{digest}  {filename}\r\n'.encode('ascii')), BytesIO(payload)]
    with patch('release_update.urllib.request.build_opener') as opener:
        opener.return_value.open.side_effect = responses
        if valid:
            assert download_setup(tmp_path, ('3.3.5', url)).read_bytes() == payload
        else:
            with pytest.raises(UpdateError):
                download_setup(tmp_path, ('3.3.5', url))
    assert sorted(file.name for file in (tmp_path / 'downloads').iterdir()) == ([filename] if valid else [])
