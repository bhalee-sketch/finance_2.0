from unittest.mock import patch

from release_update import SETUP_API, latest_setup


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
