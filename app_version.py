"""Installed builds display their release metadata; source runs use this release's version."""
import sys
from pathlib import Path
from release_update import read_json,version_key

SOURCE_VERSION='3.4.9'


def current_version():
    if not getattr(sys,'frozen',False):return SOURCE_VERSION
    try:
        version=read_json(Path(sys.executable).parent/'release.json')['version']
        version_key(version);return version
    except (OSError,ValueError,KeyError,TypeError):return None


def application_title():
    from app_profile import beta_label,source_label
    if source_label():return 'Work Space '+source_label()+' · 재무제표 테스트'
    beta=beta_label()
    if beta:return 'Work Space '+beta+' · 재무제표 테스트'
    version=current_version()
    if version is None:return 'Work Space'
    major,minor,patch=version_key(version)
    display=f'{major}.{minor}' if patch==0 else f'{major}.{minor}.{patch}'
    return f'Work Space {display}'
