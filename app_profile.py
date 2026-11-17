"""Optional packaging-only beta profile; normal source and stable builds stay unchanged."""
import json
from pathlib import Path
import re


def beta_label():
    try:
        value=json.loads((Path(__file__).resolve().parent/'build-profile.json').read_text(encoding='utf-8')).get('beta','')
        return value if isinstance(value,str) and re.fullmatch(r'3\.3-beta\.[1-9][0-9]*',value) else ''
    except (OSError,ValueError,AttributeError):return ''


def menu_groups(groups):
    if not beta_label():return groups
    return [(name,[(title,command) for title,command in cards if title=='재무제표 조회'])
            for name,cards in groups if any(title=='재무제표 조회' for title,_ in cards)]


def settings_path(original):
    if not beta_label():return original
    import shutil
    target=original.parent/('source-test' if source_label() else 'beta')/'launcher.json'
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        if original.is_file():shutil.copyfile(original,target)
    return target


def source_label():
    try:
        value=json.loads((Path(__file__).resolve().parent/'build-profile.json').read_text(encoding='utf-8')).get('source','')
        return value if isinstance(value,str) and re.fullmatch(r'source-dev\.[1-9][0-9]*',value) else ''
    except (OSError,ValueError,AttributeError):return ''
